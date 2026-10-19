"""cheap_underdog_probe.py — REAL-money 'taste' probe of ce25's validated cheap-underdog harvest. Each
btc/eth 5m window: find the UNDERDOG side (cheaper side), and if its ASK is in the target band [0.28,0.42]
(the 0.3-0.4 cell that survives taker cost at +2.7%, real-data + OOS validated), TAKER-buy a tiny bet,
diversified, hold to settle. NOT full statistical validation (that needs ~250-500 bets / ride ~$40 variance
— bad risk/reward on a compromised wallet); a small bounded 'taste' to get FIRST real execution + real-
settlement data. Hard floor caps total risk. DRY default (logs target+ask, no order); --place = real tiny.
Real PnL = WALLET, not the binance-reconstructed log (binance unreliable in this cheap band)."""
import asyncio, json, time, signal, sys, os, math, datetime
import httpx
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACE=("--place" in sys.argv)
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}
GAMMA="https://gamma-api.polymarket.com/markets"
BAND_LO=0.28; BAND_HI=0.40     # tightened to <=0.40 — thicker edge (upper band gets eaten by taker cost)
OFF_LO=30; OFF_HI=270          # buy mid-window (ce25 buys underdogs late, cheapest)
SHARES=5; DURS=[("5m",300,308,240)]
MAX_CONCURRENT=6; MAX_PER_COIN=2; MAX_TOTAL_ORDERS=40; STOP_LOSS=-22.0   # hard floor caps total risk ~$22
OUTF=os.path.join(ROOT,"data","cheap_underdog_probe.jsonl"); LOG=os.path.join(ROOT,"data","cheap_underdog_probe.log")
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
async def toks(c,slug):
    try:
        arr=(await c.get(GAMMA,params={"slug":slug},timeout=10)).json()
        if arr:
            ids=json.loads(arr[0]["clobTokenIds"]); outs=json.loads(arr[0]["outcomes"])
            return ids[outs.index("Up")],ids[outs.index("Down")]
    except: pass
    return None,None
async def topask(c,tok):
    try:
        b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok},timeout=8)).json()
        asks=sorted(float(a["price"]) for a in b.get("asks",[]) if float(a["size"])>0 and 0<float(a["price"])<1)
        return asks[0] if asks else None
    except: return None
async def our_fill(c,proxy,slug,side):
    try:
        a=(await c.get("https://data-api.polymarket.com/activity",params={"user":proxy,"limit":40},timeout=10)).json()
        fills=[(x.get("price"),x.get("size") or 0) for x in a if isinstance(x,dict) and x.get("type")=="TRADE" and (x.get("side") or "").upper()=="BUY" and x.get("slug")==slug and x.get("outcome")==side and x.get("price")]
        tot=sum(s for _,s in fills)
        if tot>0: return sum(p*s for p,s in fills)/tot
    except: pass
    return None
async def kwin(c,sym,st,wa=240):
    try:
        k1=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":st*1000,"limit":1},timeout=8)).json()
        k2=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":(st+wa)*1000,"limit":1},timeout=8)).json()
        return "Up" if float(k2[0][4])>=float(k1[0][1]) else "Down"
    except: return None
async def main():
    cli=None; proxy=None; realized=0.0; orders=0; halted=False; W={}; entered_st=set()  # one coin per window (reduce btc/eth correlated double-bet)
    if PLACE:
        cli=trader(); proxy=os.environ.get("POLY_PROXY")
        try: bal=float(cli.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6; log(f"LIVE wallet ${bal:.2f}")
        except Exception as e: log(f"bal err {str(e)[:50]}")
    async with httpx.AsyncClient() as c:
        log(f"cheap_underdog_probe START [{'LIVE --place %dsh/conc%d/maxOrd%d/stop$%g'%(SHARES,MAX_CONCURRENT,MAX_TOTAL_ORDERS,STOP_LOSS) if PLACE else 'DRY'}] buy underdog ask in [{BAND_LO},{BAND_HI}] @off{OFF_LO}-{OFF_HI}s")
        while _run:
            t=now()
            for coin,sym in COINS.items():
                for dname,dsec,settle_at,win_at in DURS:
                    ws=int(t//dsec)*dsec; slug=f"{coin}-updown-{dname}-{ws}"
                    if slug not in W:
                        up,dn=await toks(c,slug)
                        if up: W[slug]={"coin":coin,"sym":sym,"st":ws,"up":up,"dn":dn,"entered":False,"order":None,"settled":False,"settle_at":settle_at,"win_at":win_at}
            for slug,w in list(W.items()):
                sec=t-w["st"]
                if not w["entered"] and OFF_LO<=sec<=OFF_HI:
                    # find the underdog (cheaper) side and its ask
                    aU=await topask(c,w["up"]); aD=await topask(c,w["dn"])
                    if aU and aD:
                        side,ask,tok=("Up",aU,w["up"]) if aU<aD else ("Down",aD,w["dn"])
                        if BAND_LO<=ask<=BAND_HI and w["st"] not in entered_st:
                            liveN=sum(1 for ww in W.values() if ww.get("order") and not ww["order"].get("done"))
                            coinN=sum(1 for ww in W.values() if ww["coin"]==w["coin"] and ww.get("order") and not ww["order"].get("done"))
                            if PLACE and (halted or orders>=MAX_TOTAL_ORDERS or realized<=STOP_LOSS):
                                if realized<=STOP_LOSS and not halted: log("=== STOP-LOSS HALT ==="); halted=True
                            elif PLACE and (liveN>=MAX_CONCURRENT or coinN>=MAX_PER_COIN): pass
                            else:
                                if PLACE:
                                    placed=round(min(ask+0.01,0.97),2)
                                    try:
                                        r=cli.place_limit_order(token_id=tok,price=placed,size=SHARES,side="BUY",post_only=False)
                                        oid=getattr(r,"order_id",None) or getattr(r,"id",None)
                                    except Exception as ex: log(f"  err {slug}: {str(ex)[:70]}"); w["entered"]=True; continue
                                    if not oid: w["entered"]=True; continue
                                    orders+=1; log(f"*** UNDERDOG #{orders} {slug} {side} {SHARES}sh @~{ask:.3f}(off{sec:.0f}s) ***")
                                    w["entered"]=True; entered_st.add(w["st"]); w["order"]={"side":side,"ask":round(ask,3),"placed":placed,"paid":None,"oid":oid,"filled":False,"off":round(sec)}
                                else:
                                    log(f"[DRY] underdog {slug} {side} ask {ask:.3f} @off{sec:.0f}s (would buy)")
                                    w["entered"]=True; entered_st.add(w["st"]); w["order"]={"side":side,"ask":round(ask,3),"placed":round(ask,3),"paid":round(ask,3),"oid":None,"filled":True,"off":round(sec)}
                if PLACE and cli and w.get("order") and not w["order"]["filled"]:
                    o=w["order"]
                    try:
                        od=cli.get_order(order_id=o["oid"]); mt=float(getattr(od,"size_matched",0) or 0)
                        if mt>=SHARES-1e-6:
                            rp=await our_fill(c,proxy,slug,o["side"]); o["paid"]=round(rp,3) if rp else o["placed"]; o["filled"]=True
                            log(f"  FILLED {slug} real@{o['paid']:.3f} (ask{o['ask']:.3f})")
                    except: pass
                if sec>w["settle_at"] and not w["settled"]:
                    w["settled"]=True; o=w.get("order")
                    if o:
                        if PLACE and cli and not o["filled"]:
                            try: cli.cancel_order(order_id=o["oid"])
                            except: pass
                            o["done"]=True; log(f"SETTLE {slug} unfilled->cancel")
                        else:
                            win=await kwin(c,w["sym"],w["st"],w["win_at"]); won=(o["side"]==win) if win else None
                            paid=o["paid"] if o["paid"] is not None else o["placed"]
                            pnl=(((1-paid) if won else -paid)*SHARES) if won is not None else 0.0
                            if PLACE and won is not None: realized+=pnl
                            o["done"]=True
                            row={"slug":slug,"coin":w["coin"],"side":o["side"],"winner":win,"won":won,"ask":o["ask"],"paid":round(paid,3),"off":o["off"],"pnl":round(pnl,2),"live":PLACE,"note":"binance_outcome_noisy"}
                            open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
                            log(f"SETTLE {slug} {o['side']} paid@{paid:.3f} {'WON' if won else 'LOST'} pnl=${pnl:+.2f}{' cum$%+.2f'%realized if PLACE else ''}")
                    del W[slug]
            await asyncio.sleep(4)
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
