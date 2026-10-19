"""early_trend_maker.py — test if a MAKER, posting EARLY on the TREND-aligned (binance z>=2.5) favorite side,
can fill at a GOOD (cheap) price (eebde ~0.67-0.75) rather than z-maker's late 0.85+. Posts a post_only bid
at the best bid early (off 15-90s) on the z>=2.5 lead side; measures FILL RATE (or did price run away=miss),
real FILL PRICE, and discount vs the ask at post time. The honest question: cheap fills, or adverse/miss?
DRY default (shows would-post bid+ask, no order — can't know fills). --place = real tiny (measures fills).
Real PnL = wallet. Caps + hard floor. NOTE: judge by FILL PRICE + FILL RATE, not small-sample PnL."""
import asyncio, json, time, signal, sys, os, math, datetime
import httpx
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACE=("--place" in sys.argv)
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}; GAMMA="https://gamma-api.polymarket.com/markets"
ENTRY_Z=2.0; OFF_LO=15; OFF_HI=140; CANCEL_AT=200   # LOOSENED 2026-06-09: z2.5->2.0, window 90->140s, cancel 150->200 (was ~dormant: 0 fills/49min, z>=2.5 early too rare)
SHARES=5; DURS=[("5m",300,308,240)]
MAX_CONCURRENT=4; MAX_PER_COIN=1; MAX_TOTAL_ORDERS=40; STOP_LOSS=-18.0
OUTF=os.path.join(ROOT,"data","early_trend_maker.jsonl"); LOG=os.path.join(ROOT,"data","early_trend_maker.log")
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
_vol={"t":0,"v":{}}
async def vol30(c,sym):
    if time.time()-_vol["t"]<90 and sym in _vol["v"]: return _vol["v"][sym]
    try:
        k=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","limit":31},timeout=8)).json()
        cl=[float(x[4]) for x in k]; r=[math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))]
        m=sum(r)/len(r); v=(sum((x-m)**2 for x in r)/len(r))**0.5; _vol["v"][sym]=v; _vol["t"]=time.time(); return v
    except: return None
async def toks(c,slug):
    try:
        a=(await c.get(GAMMA,params={"slug":slug},timeout=10)).json()
        if a: ids=json.loads(a[0]["clobTokenIds"]); outs=json.loads(a[0]["outcomes"]); return ids[outs.index("Up")],ids[outs.index("Down")]
    except: pass
    return None,None
async def bidask(c,tok):
    try:
        b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok},timeout=8)).json()
        bids=sorted((float(a["price"]) for a in b.get("bids",[]) if float(a["size"])>0 and 0<float(a["price"])<1),reverse=True)
        asks=sorted(float(a["price"]) for a in b.get("asks",[]) if float(a["size"])>0 and 0<float(a["price"])<1)
        return (bids[0] if bids else None),(asks[0] if asks else None)
    except: return None,None
async def our_fill(c,proxy,slug,side):
    try:
        a=(await c.get("https://data-api.polymarket.com/activity",params={"user":proxy,"limit":40},timeout=10)).json()
        f=[(x.get("price"),x.get("size") or 0) for x in a if isinstance(x,dict) and x.get("type")=="TRADE" and (x.get("side") or "").upper()=="BUY" and x.get("slug")==slug and x.get("outcome")==side and x.get("price")]
        tot=sum(s for _,s in f)
        if tot>0: return sum(p*s for p,s in f)/tot
    except: pass
    return None
async def kwin(c,sym,st,wa=240):
    try:
        k1=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":st*1000,"limit":1},timeout=8)).json()
        k2=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":(st+wa)*1000,"limit":1},timeout=8)).json()
        return "Up" if float(k2[0][4])>=float(k1[0][1]) else "Down"
    except: return None
async def main():
    cli=None; proxy=None; realized=0.0; orders=0; halted=False; W={}
    if PLACE:
        cli=trader(); proxy=os.environ.get("POLY_PROXY")
        try: log(f"LIVE wallet ${float(cli.get_balance_allowance(asset_type='COLLATERAL').balance)/1e6:.2f}")
        except Exception as e: log(f"bal err {str(e)[:40]}")
    async with httpx.AsyncClient() as c:
        log(f"early_trend_maker START [{'LIVE %dsh/stop$%g'%(SHARES,STOP_LOSS) if PLACE else 'DRY'}] post bid early(off{OFF_LO}-{OFF_HI}s) on z>={ENTRY_Z} lead side")
        while _run:
            t=now()
            for coin,sym in COINS.items():
                for dn,dsec,settle_at,win_at in DURS:
                    ws=int(t//dsec)*dsec; slug=f"{coin}-updown-{dn}-{ws}"
                    if slug not in W:
                        up,dd=await toks(c,slug)
                        if up: W[slug]={"coin":coin,"sym":sym,"st":ws,"up":up,"dn":dd,"open":await kopen(c,sym,ws),"entered":False,"order":None,"settled":False,"settle_at":settle_at,"win_at":win_at}
            for slug,w in list(W.items()):
                sec=t-w["st"]
                if w["open"] is None: w["open"]=await kopen(c,w["sym"],w["st"]); continue
                if not w["entered"] and OFF_LO<=sec<=OFF_HI:
                    px=await bpx(c,w["sym"]); v=await vol30(c,w["sym"])
                    if px and v:
                        lead=math.log(px/w["open"])*1e4; z=abs(lead)/v if v else 0; side="Up" if lead>=0 else "Down"
                        if z>=ENTRY_Z:
                            tok=w["up"] if side=="Up" else w["dn"]; bid,ask=await bidask(c,tok)
                            if bid and ask:
                                liveN=sum(1 for ww in W.values() if ww.get("order") and not ww["order"].get("done"))
                                coinN=sum(1 for ww in W.values() if ww["coin"]==w["coin"] and ww.get("order") and not ww["order"].get("done"))
                                if PLACE and (halted or orders>=MAX_TOTAL_ORDERS or realized<=STOP_LOSS):
                                    if realized<=STOP_LOSS and not halted: log("=== STOP-LOSS HALT ==="); halted=True
                                elif PLACE and (liveN>=MAX_CONCURRENT or coinN>=MAX_PER_COIN): pass
                                else:
                                    if PLACE:
                                        try:
                                            r=cli.place_limit_order(token_id=tok,price=round(bid,2),size=SHARES,side="BUY",post_only=True)
                                            oid=getattr(r,"order_id",None) or getattr(r,"id",None)
                                        except Exception as ex:
                                            m=str(ex)[:60]; log(f"  err {slug}:{m}")
                                            if "crosses" not in m: w["entered"]=True  # crosses-book = retry next poll (book moved), don't abandon window
                                            continue
                                        if not oid: w["entered"]=True; continue
                                        orders+=1; log(f"*** BID #{orders} {slug} {side} {SHARES}sh @ {bid:.3f} (ask{ask:.3f} z{z:.1f}@{sec:.0f}s) ***")
                                        w["entered"]=True; w["order"]={"side":side,"bid":round(bid,3),"ask0":round(ask,3),"oid":oid,"filled":False,"paid":None,"z":round(z,1),"off":round(sec)}
                                    else:
                                        log(f"[DRY] would post {slug} {side} bid{bid:.3f} (ask{ask:.3f} disc{(ask-bid)*100:.1f}c z{z:.1f}@{sec:.0f}s)")
                                        w["entered"]=True; w["order"]={"side":side,"bid":round(bid,3),"ask0":round(ask,3),"oid":None,"filled":True,"paid":round(bid,3),"z":round(z,1),"off":round(sec)}
                # poll fill + cancel-if-unfilled-by-CANCEL_AT
                if PLACE and cli and w.get("order") and not w["order"]["filled"] and not w["order"].get("done"):
                    o=w["order"]
                    try:
                        od=cli.get_order(order_id=o["oid"]); mt=float(getattr(od,"size_matched",0) or 0)
                        if mt>=SHARES-1e-6:
                            rp=await our_fill(c,proxy,slug,o["side"]); o["paid"]=round(rp,3) if rp else o["bid"]; o["filled"]=True
                            log(f"  FILLED {slug} @ {o['paid']:.3f} (bid{o['bid']:.3f} ask0{o['ask0']:.3f})")
                    except: pass
                    if sec>CANCEL_AT and not o["filled"]:
                        try: cli.cancel_order(order_id=o["oid"])
                        except: pass
                        o["done"]=True; o["missed"]=True
                        log(f"  MISSED {slug} unfilled by {CANCEL_AT}s -> cancel (price ran away)")
                        open(OUTF,"a",encoding="utf-8").write(json.dumps({"slug":slug,"coin":w["coin"],"side":o["side"],"bid":o["bid"],"ask0":o["ask0"],"missed":True,"z":o["z"],"off":o["off"],"live":PLACE})+"\n")
                if sec>w["settle_at"] and not w["settled"]:
                    w["settled"]=True; o=w.get("order")
                    if o and o.get("filled"):
                        win=await kwin(c,w["sym"],w["st"],w["win_at"]); won=(o["side"]==win) if win else None
                        paid=o["paid"]; pnl=(((1-paid) if won else -paid)*SHARES) if won is not None else 0.0
                        if PLACE and won is not None: realized+=pnl
                        row={"slug":slug,"coin":w["coin"],"side":o["side"],"won":won,"bid":o["bid"],"ask0":o["ask0"],"paid":round(paid,3),"disc_c":round((o["ask0"]-paid)*100,1),"z":o["z"],"off":o["off"],"pnl":round(pnl,2),"missed":False,"live":PLACE}
                        open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
                        log(f"SETTLE {slug} {o['side']} fill@{paid:.3f}(ask0{o['ask0']:.3f} disc{row['disc_c']:.1f}c) {'WON' if won else 'LOST'} ${pnl:+.2f}{' cum$%+.2f'%realized if PLACE else ''}")
                    del W[slug]
            await asyncio.sleep(4)
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
