"""strength_maker_live.py — REAL-money validation of the confirmed-strengthening MAKER (user's insight, passive
probe showed +EV at deep tiers). The ONE thing passive can't answer: do REAL resting bids actually FILL at the
discount, and is the filled subset adversely selected? Per btc/eth 5m window, at checkpoints [60,90,120,150]:
detect CONFIRMED STRENGTHENING (lead>=STRONG=8 AND growing >=+GROW=2 vs 30s ago, same side); place a REAL
post_only BUY at mid-DISC (mid-4c, the +EV zone) on the strengthening side; if unfilled by CANCEL_AT, cancel
(the pullback never came). Hold filled to settle. Measures REAL fill-rate + win + PnL.
  DRY default: logs would-be. --place: REAL tiny orders. HARD CAPS. Real PnL = wallet. -> data/strength_maker_live.jsonl"""
import asyncio, json, time, signal, sys, os, math, datetime
import httpx
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACE=("--place" in sys.argv)
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}; GAMMA="https://gamma-api.polymarket.com/markets"
STRONG=8.0; GROW=2.0; CPS=[60,90,120,150]; DISC=0.04   # confirmed-strengthening; bid at mid-4c (the +EV deep tier)
SHARES=5; CANCEL_AT=200; SETTLE=308; WIN_AT=240
MAX_CONCURRENT=3; MAX_PER_COIN=1; MAX_TOTAL_ORDERS=120; STOP_LOSS=-15.0; PRICE_CAP=0.97
OUTF=os.path.join(ROOT,"data","strength_maker_live.jsonl"); LOG=os.path.join(ROOT,"data","strength_maker_live.log")
_run=True
def _sig(*_):
    global _run; _run=False
signal.signal(signal.SIGINT,_sig)
def now(): return time.time()
def log(m):
    line=f"[{datetime.datetime.utcnow().strftime('%H:%M:%S')}] {m}"; print(line,flush=True)
    try: open(LOG,"a",encoding="utf-8").write(line+"\n")
    except: pass
def load_env():
    for l in open(os.path.join(ROOT,".env"),encoding="utf-8"):
        if "=" in l and not l.startswith("#"):
            k,v=l.strip().split("=",1); os.environ.setdefault(k.strip(),v.strip())
    return os.environ["POLY_PK"],os.environ["POLY_PROXY"]
def trader():
    pk,proxy=load_env(); from polymarket import SecureClient
    return SecureClient.create(private_key=pk,wallet=proxy)
async def bpx(c,sym):
    try: return float((await c.get("https://api.binance.com/api/v3/ticker/price",params={"symbol":sym},timeout=8)).json()["price"])
    except: return None
async def kopen(c,sym,st):
    try: return float((await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":st*1000,"limit":1},timeout=8)).json()[0][1])
    except: return None
async def toks(c,slug):
    try:
        a=(await c.get(GAMMA,params={"slug":slug},timeout=10)).json()
        if a: ids=json.loads(a[0]["clobTokenIds"]); outs=json.loads(a[0]["outcomes"]); return ids[outs.index("Up")],ids[outs.index("Down")]
    except: pass
    return None,None
async def book(c,tok):
    try:
        b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok},timeout=8)).json()
        bids=sorted((float(a["price"]) for a in b.get("bids",[]) if float(a["size"])>0 and 0<float(a["price"])<1),reverse=True)
        asks=sorted(float(a["price"]) for a in b.get("asks",[]) if float(a["size"])>0 and 0<float(a["price"])<1)
        return (bids[0] if bids else None),(asks[0] if asks else None)
    except: return None,None
async def kwin(c,sym,st,wa=240):
    try:
        k1=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":st*1000,"limit":1},timeout=8)).json()
        k2=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":(st+wa)*1000,"limit":1},timeout=8)).json()
        return "Up" if float(k2[0][4])>=float(k1[0][1]) else "Down"
    except: return None
async def main():
    cli=None; realized=0.0; orders=0; halted=False; W={}
    if PLACE:
        cli=trader()
        try: log(f"LIVE wallet ${float(cli.get_balance_allowance(asset_type='COLLATERAL').balance)/1e6:.2f}")
        except Exception as e: log(f"bal err {str(e)[:40]}")
    async with httpx.AsyncClient() as c:
        log(f"strength_maker_live START [{'LIVE --place %dsh/conc%d/stop$%g'%(SHARES,MAX_CONCURRENT,STOP_LOSS) if PLACE else 'DRY'}] post mid-{int(DISC*100)}c on CONFIRMED-STRENGTHENING (lead>={STRONG} & grow>={GROW})")
        while _run:
            t=now()
            for coin,sym in COINS.items():
                ws=int(t//300)*300; slug=f"{coin}-updown-5m-{ws}"
                if slug not in W:
                    up,dn=await toks(c,slug)
                    if up: W[slug]={"coin":coin,"sym":sym,"st":ws,"up":up,"dn":dn,"open":await kopen(c,sym,ws),
                                    "leadhist":{},"order":None,"entered":False,"settled":False}
            for slug,w in list(W.items()):
                sec=t-w["st"]
                if w["open"] is None: w["open"]=await kopen(c,w["sym"],w["st"]); continue
                # detect confirmed strengthening at checkpoints, place bid
                if not w["entered"]:
                    for cp in CPS:
                        if cp in w["leadhist"] or sec<cp or sec>cp+25: continue  # widened 12->25s catch window (poll/await delays were missing checkpoints)
                        px=await bpx(c,w["sym"])
                        if not px: break
                        lead=math.log(px/w["open"])*1e4; w["leadhist"][cp]=lead; prev=w["leadhist"].get(cp-30)
                        if abs(lead)<STRONG: break
                        if prev is None or (lead>=0)!=(prev>=0) or abs(lead)<abs(prev)+GROW: break
                        side="Up" if lead>=0 else "Down"; tok=w["up"] if side=="Up" else w["dn"]
                        bid,ask=await book(c,tok)
                        if bid is None or ask is None: break
                        mid=(bid+ask)/2; price=round(min(mid-DISC,PRICE_CAP),2)
                        if price<=0.05: break
                        # cross-strategy DEDUP: skip if early_taker already took this window (avoid the double-up that caused -$22.78)
                        try:
                            et=open(os.path.join(ROOT,"data","early_taker_probe.jsonl"),encoding="utf-8").readlines()[-80:]
                            if slug in set(json.loads(l).get("slug") for l in et if l.strip() and '"kind": "entry"' in l):
                                log(f"  DEDUP-SKIP {slug} (early_taker took it -> no double-up)"); w["entered"]=True; break
                        except: pass
                        liveN=sum(1 for ww in W.values() if ww.get("order") and not ww["order"].get("done"))
                        coinN=sum(1 for ww in W.values() if ww["coin"]==w["coin"] and ww.get("order") and not ww["order"].get("done"))
                        if PLACE and (halted or orders>=MAX_TOTAL_ORDERS or realized<=STOP_LOSS):
                            if realized<=STOP_LOSS and not halted: log("=== STOP-LOSS HALT ==="); halted=True
                            w["entered"]=True; break
                        if PLACE and (liveN>=MAX_CONCURRENT or coinN>=MAX_PER_COIN): w["entered"]=True; break
                        if PLACE:
                            try:
                                r=cli.place_limit_order(token_id=tok,price=price,size=SHARES,side="BUY",post_only=True)
                                oid=getattr(r,"order_id",None) or getattr(r,"id",None)
                            except Exception as ex: log(f"  place-err {slug}:{str(ex)[:70]}"); w["entered"]=True; break
                            if not oid: w["entered"]=True; break
                            orders+=1; w["order"]={"side":side,"price":price,"mid":round(mid,3),"ask0":round(ask,3),"oid":oid,"filled":False,"cp":cp,"lead":round(lead,1)}
                            w["entered"]=True
                            log(f"*** S-MAKER #{orders} {slug} {side} {SHARES}sh @ {price} (mid{mid:.3f} ask{ask:.3f} lead{lead:+.0f}@{cp}s grow) ***")
                        else:
                            w["order"]={"side":side,"price":price,"mid":round(mid,3),"ask0":round(ask,3),"oid":None,"filled":False,"cp":cp,"lead":round(lead,1)}
                            w["entered"]=True
                            log(f"[DRY] would post {slug} {side} @ {price} (mid{mid:.3f} lead{lead:+.0f}@{cp}s)")
                        break
                # poll fill
                o=w.get("order")
                if PLACE and cli and o and not o["filled"] and not o.get("done"):
                    try:
                        od=cli.get_order(order_id=o["oid"]); mt=float(getattr(od,"size_matched",0) or 0)
                        if mt>=SHARES-1e-6: o["filled"]=True; log(f"  *** FILLED {slug} {o['side']} @ {o['price']} ***")
                    except: pass
                    if sec>CANCEL_AT and not o["filled"]:
                        try: cli.cancel_order(order_id=o["oid"])
                        except: pass
                        o["done"]=True; o["missed"]=True
                        log(f"  MISSED {slug} unfilled by {CANCEL_AT}s -> cancel (no pullback)")
                # settle
                if sec>SETTLE and not w["settled"]:
                    w["settled"]=True; win=await kwin(c,w["sym"],w["st"],WIN_AT)
                    if o and o["filled"] and win:
                        won=(o["side"]==win); pnl=((1-o["price"]) if won else -o["price"])*SHARES
                        if PLACE: realized+=pnl
                        row={"slug":slug,"coin":w["coin"],"side":o["side"],"winner":win,"won":won,"price":o["price"],"mid":o["mid"],"ask0":o["ask0"],"disc_c":round((o["mid"]-o["price"])*100,1),"lead":o["lead"],"cp":o["cp"],"pnl":round(pnl,2),"live":PLACE}
                        open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
                        log(f"SETTLE {slug} win={win} {o['side']} @{o['price']} {'WON' if won else 'LOST'} ${pnl:+.2f}{' cum$%+.2f'%realized if PLACE else ''}")
                    elif o and (o.get("missed") or not o["filled"]):
                        open(OUTF,"a",encoding="utf-8").write(json.dumps({"slug":slug,"coin":w["coin"],"side":o["side"],"missed":True,"price":o["price"],"lead":o["lead"],"cp":o["cp"],"live":PLACE})+"\n")
                    del W[slug]
            await asyncio.sleep(4)
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
