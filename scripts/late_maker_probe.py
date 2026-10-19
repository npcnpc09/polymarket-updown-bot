"""late_maker_probe.py — OBSERVE-ONLY. Test eebde's decoded edge: LATE-window MAKER
spread capture. In the final (1-LATE_FRAC) of a window, on the side the underlying leads,
post a hypothetical maker BID at best_bid+1tick (capturing the wide late spread that a
taker pays as ask). Mark FILLED if the ask drops to our bid. At settle, resolution from the
converged mid. Reports: fill rate, WR_filled vs WR_signal (late adverse selection?),
maker_EV at our bid vs taker_EV at the ask. If late maker fills at ~0.78 with high WR ->
this is eebde's +$919k engine, replicable. Row -> data/late_maker.jsonl
"""
import asyncio, json, time, signal, sys, math, datetime
from collections import defaultdict
import httpx
try: import websockets
except ImportError: print("pip install websockets"); sys.exit(1)
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
ASSETS={"btc":"BTC-USD","eth":"ETH-USD","sol":"SOL-USD","xrp":"XRP-USD","doge":"DOGE-USD"}
PROD2COIN={v:k for k,v in ASSETS.items()}
THR_BPS=5.0; LATE_FRAC=0.80; MIN_TTL=15; YR=31557600.0
CB_WS="wss://ws-feed.exchange.coinbase.com"
CB_CANDLES="https://api.exchange.coinbase.com/products/{p}/candles"
GAMMA="https://gamma-api.polymarket.com/markets"
OUTF="data/late_maker.jsonl"; LOG="data/late_maker.log"
_run=True
def _sig(*_):
    global _run; _run=False
signal.signal(signal.SIGINT,_sig)
def now(): return time.time()
def log(m):
    line=f"[{datetime.datetime.utcnow().strftime('%H:%M:%S')}] {m}"; print(line,flush=True)
    try: open(LOG,"a",encoding="utf-8").write(line+"\n")
    except: pass
class S:
    def __init__(s):
        s.px=defaultdict(lambda:None); s.bids=defaultdict(dict); s.asks=defaultdict(dict)
        s.win={}; s.orders={}; s.stats=defaultdict(int)
def _prune(b,k,hi):
    if len(b)<=k*2: return
    ks=sorted(b); drop=ks[:-k] if hi else ks[k:]
    for p in drop: b.pop(p,None)
async def cb_ws(s):
    d=1
    while _run:
        try:
            async with websockets.connect(CB_WS,ping_interval=15,open_timeout=12,max_size=16*1024*1024) as ws:
                await ws.send(json.dumps({"type":"subscribe","product_ids":list(ASSETS.values()),"channels":["level2_batch"]}))
                log(f"Coinbase level2 connected {list(ASSETS)}"); d=1
                while _run:
                    m=json.loads(await asyncio.wait_for(ws.recv(),timeout=30))
                    t=m.get("type"); c=PROD2COIN.get(m.get("product_id"))
                    if not c: continue
                    if t=="snapshot":
                        s.bids[c]={float(p):float(z) for p,z in m.get("bids",[])[:300]}
                        s.asks[c]={float(p):float(z) for p,z in m.get("asks",[])[:300]}
                    elif t=="l2update":
                        for ch in m.get("changes",[]):
                            sd,p,z=ch[0],float(ch[1]),float(ch[2]); bk=s.bids[c] if sd=="buy" else s.asks[c]
                            if z==0: bk.pop(p,None)
                            else: bk[p]=z
                        _prune(s.bids[c],300,True); _prune(s.asks[c],300,False)
                    else: continue
                    bb=max(s.bids[c]) if s.bids[c] else None; ba=min(s.asks[c]) if s.asks[c] else None
                    if bb and ba and ba>bb: s.px[c]=(bb+ba)/2; s.stats["ticks"]+=1
        except Exception as e:
            if not _run: break
            log(f"cb err {str(e)[:40]}"); await asyncio.sleep(d); d=min(30,d*2)
async def cb_open(c,prod,st):
    try:
        iso=lambda t: datetime.datetime.utcfromtimestamp(t).isoformat()
        r=(await c.get(CB_CANDLES.format(p=prod),params={"granularity":60,"start":iso(st-180),"end":iso(st+120)})).json()
        if isinstance(r,list) and r:
            for cd in r:
                if int(cd[0])==st: return float(cd[3])
            return float(min(r,key=lambda cd:abs(int(cd[0])-st))[3])
    except: pass
    return None
async def discovery(s):
    while _run:
        t=int(now())
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                for coin,prod in ASSETS.items():
                    for mt,du in (("5m",300),("15m",900)):
                        base=(t//du)*du
                        for st in (base,base+du):
                            slug=f"{coin}-updown-{mt}-{st}"; settle=st+du; ttl=settle-now()
                            if ttl<MIN_TTL or ttl>du+60 or slug in s.win: continue
                            try:
                                arr=(await c.get(GAMMA,params={"slug":slug})).json()
                                if not arr or arr[0].get("closed"): continue
                                m=arr[0]; ids=json.loads(m["clobTokenIds"]); outs=json.loads(m["outcomes"])
                                up=ids[outs.index("Up")]; dn=ids[outs.index("Down")]; op=await cb_open(c,prod,st)
                                s.win[slug]={"coin":coin,"prod":prod,"start":st,"settle":settle,"dur":du,"up":up,"dn":dn,"open":op}
                            except: continue
                for slug,w in list(s.win.items()):
                    if w["open"] is None and w["settle"]-now()>0: w["open"]=await cb_open(c,w["prod"],w["start"])
                    if w["settle"]-now()<-200 and slug not in s.orders: del s.win[slug]
        except Exception as e: log(f"disc {str(e)[:30]}")
        for _ in range(8):
            if not _run: break
            await asyncio.sleep(1)
async def pm_book(tok):
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok})).json()
        asks=sorted(float(a["price"]) for a in b.get("asks",[]) if float(a["size"])>0 and float(a["price"])<1)
        bids=sorted((float(a["price"]) for a in b.get("bids",[]) if float(a["size"])>0 and float(a["price"])>0),reverse=True)
        return (bids[0] if bids else None),(asks[0] if asks else None)
    except: return None,None
async def signal_loop(s):
    while _run:
        for slug,w in list(s.win.items()):
            ttl=w["settle"]-now(); px=s.px.get(w["coin"])
            if w["open"] is None or px is None or slug in s.orders or ttl<MIN_TTL: continue
            elapsed=(now()-w["start"])/w["dur"]
            if elapsed<LATE_FRAC: continue                          # LATE only
            lead=math.log(px/w["open"])*1e4
            if abs(lead)<THR_BPS: continue
            side="Up" if lead>=0 else "Down"; tok=w["up"] if side=="Up" else w["dn"]
            bid,ask=await pm_book(tok)
            if bid is None or ask is None: continue
            B=round(bid+0.01,2)                                     # post maker bid 1 tick above best bid (capture spread)
            if B>=ask: B=bid                                        # if spread is 1 tick, just join the bid
            if not (0.30<=B<=0.97): continue
            s.orders[slug]={"coin":w["coin"],"side":side,"lead":round(lead,1),"ttl":int(ttl),
                "B":B,"bid":bid,"ask":ask,"spread":round(ask-bid,3),"tok":tok,"settle":w["settle"],
                "filled":False,"conv":None,"_done":False,"_lp":0}
            s.stats["fired"]+=1
            log(f"LATE {slug} {side} lead={lead:.0f}bps ttl={int(ttl)}s bid={bid} ask={ask} spread={round(ask-bid,2)} postB={B}")
        for slug,o in list(s.orders.items()):
            if o["_done"]: continue
            if now()-o["_lp"]>2 and o["settle"]-now()>-5:
                o["_lp"]=now(); bid,ask=await pm_book(o["tok"])
                if ask is not None and ask<=o["B"] and not o["filled"]:
                    o["filled"]=True; log(f"  FILL {slug} ask {ask}<=B {o['B']}")
                if bid is not None and ask is not None and o["settle"]-now()<70: o["conv"]=(bid+ask)/2
            if o["settle"]-now()<-15: await finalize(s,slug,o)
        await asyncio.sleep(1)
async def finalize(s,slug,o):
    o["_done"]=True; cp=o.get("conv")
    win=(cp>=0.5) if cp is not None else None
    ev_maker=((1.0/o["B"]-1.0) if win else -1.0) if (o["filled"] and win is not None) else None
    ev_taker=((1.0/o["ask"]-1.0) if win else -1.0) if win is not None else None
    row={"slug":slug,"coin":o["coin"],"side":o["side"],"lead":o["lead"],"ttl":o["ttl"],
         "B":o["B"],"bid":o["bid"],"ask":o["ask"],"spread":o["spread"],"filled":o["filled"],
         "sig_win":win,"maker_ev":round(ev_maker,3) if ev_maker is not None else None,
         "taker_ev":round(ev_taker,3) if ev_taker is not None else None}
    open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
    s.stats["settled"]+=1
    if o["filled"]: s.stats["filled"]+=1
    log(f"DONE {slug} filled={o['filled']} win={win} maker_ev={row['maker_ev']} taker_ev={row['taker_ev']}")
    del s.orders[slug]
async def reporter(s):
    await asyncio.sleep(20)
    while _run:
        rows=[]
        try:
            for ln in open(OUTF,encoding="utf-8"): rows.append(json.loads(ln))
        except: pass
        sig=[r for r in rows if r.get("sig_win") is not None]
        fil=[r for r in sig if r["filled"]]
        def wr(rs): return f"{sum(1 for r in rs if r['sig_win'])/len(rs)*100:.0f}%(n{len(rs)})" if rs else "na"
        mev=f"{sum(r['maker_ev'] for r in fil)/len(fil)*100:+.1f}%" if fil else "na"
        tev=f"{sum(r['taker_ev'] for r in sig)/len(sig)*100:+.1f}%" if sig else "na"
        avgB=f"{sum(r['B'] for r in fil)/len(fil):.2f}" if fil else "na"
        avgsp=f"{sum(r['spread'] for r in sig)/len(sig):.2f}" if sig else "na"
        log(f"STAT ticks={s.stats['ticks']} win={len(s.win)} fired={s.stats['fired']} settled={len(sig)} "
            f"fill_rate={len(fil)}/{len(sig)} avgB={avgB} avg_spread={avgsp} | "
            f"WR_sig={wr(sig)} WR_fill={wr(fil)} | maker_EV={mev} vs taker_EV={tev}")
        for _ in range(30):
            if not _run: break
            await asyncio.sleep(1)
async def main():
    s=S(); log(f"late_maker_probe OBSERVE-ONLY LATE_FRAC={LATE_FRAC} thr={THR_BPS}bps (post bid+1tick on leading side)")
    await asyncio.gather(cb_ws(s),discovery(s),signal_loop(s),reporter(s))
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
