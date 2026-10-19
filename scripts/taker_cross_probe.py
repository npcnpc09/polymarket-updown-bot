"""taker_cross_probe.py — OBSERVE-ONLY paper probe for the BIG-MOVE TAKER edge.
When the underlying's |lead| (vs window open, Coinbase mid) first crosses THR bps, record
the leading side's REAL Polymarket ASK (taker entry) + bid/spread + ttl. At settle, read the
converged price (actual resolution) and compute realized taker EV AT THE REAL ASK (and at mid
for comparison). Validates whether the backtested +20% (mid-based) survives the real spread.
No orders, no money. Row -> data/taker_cross.jsonl
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
THR_BPS=20.0; MIN_TTL=30; YR=31557600.0
CB_WS="wss://ws-feed.exchange.coinbase.com"
CB_CANDLES="https://api.exchange.coinbase.com/products/{p}/candles"
GAMMA="https://gamma-api.polymarket.com/markets"
OUTF="data/taker_cross.jsonl"; LOG="data/taker_cross.log"
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
                                s.win[slug]={"coin":coin,"prod":prod,"start":st,"settle":settle,"up":up,"dn":dn,"open":op}
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
            lead=math.log(px/w["open"])*1e4
            if abs(lead)<THR_BPS: continue
            side="Up" if lead>=0 else "Down"; tok=w["up"] if side=="Up" else w["dn"]
            bid,ask=await pm_book(tok)
            if ask is None or bid is None: continue
            s.orders[slug]={"coin":w["coin"],"side":side,"lead":round(lead,1),"ttl":int(ttl),
                "ask":ask,"bid":bid,"spread":round(ask-bid,3),"tok":tok,"settle":w["settle"],
                "conv":None,"_done":False,"_lp":0}
            s.stats["fired"]+=1
            log(f"CROSS {slug} {side} lead={lead:.0f}bps ttl={int(ttl)}s ask={ask} bid={bid} spread={round(ask-bid,2)}")
        for slug,o in list(s.orders.items()):
            if o["_done"]: continue
            if now()-o["_lp"]>3 and o["settle"]-now()>-5:
                o["_lp"]=now(); bid,ask=await pm_book(o["tok"])
                if bid is not None and ask is not None and o["settle"]-now()<75: o["conv"]=(bid+ask)/2
            if o["settle"]-now()<-15: await finalize(s,slug,o)
        await asyncio.sleep(1)
async def finalize(s,slug,o):
    o["_done"]=True; cp=o.get("conv")
    win=(cp>=0.5) if cp is not None else None
    ev_ask=((1.0/o["ask"]-1.0) if win else -1.0) if win is not None else None
    mid=(o["ask"]+o["bid"])/2
    ev_mid=((1.0/mid-1.0) if win else -1.0) if win is not None else None
    row={"slug":slug,"coin":o["coin"],"side":o["side"],"lead":o["lead"],"ttl":o["ttl"],
         "ask":o["ask"],"bid":o["bid"],"spread":o["spread"],"win":win,
         "ev_ask":round(ev_ask,3) if ev_ask is not None else None,
         "ev_mid":round(ev_mid,3) if ev_mid is not None else None}
    open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
    s.stats["settled"]+=1
    log(f"DONE {slug} win={win} ev_ask={row['ev_ask']} ev_mid={row['ev_mid']}")
    del s.orders[slug]
async def reporter(s):
    await asyncio.sleep(20)
    while _run:
        rows=[]
        try:
            for ln in open(OUTF,encoding="utf-8"): rows.append(json.loads(ln))
        except: pass
        v=[r for r in rows if r.get("win") is not None]
        def agg(rs):
            if not rs: return "na"
            wr=sum(1 for r in rs if r["win"])/len(rs)*100
            ea=sum(r["ev_ask"] for r in rs)/len(rs)*100
            em=sum(r["ev_mid"] for r in rs)/len(rs)*100
            ak=sum(r["ask"] for r in rs)/len(rs); sp=sum(r["spread"] for r in rs)/len(rs)
            return f"n={len(rs)} WR={wr:.0f}% ask={ak:.2f} spread={sp:.2f} EV_ask={ea:+.1f}% EV_mid={em:+.1f}%"
        log(f"STAT ticks={s.stats['ticks']} win={len(s.win)} fired={s.stats['fired']} | ALL {agg(v)}")
        # by ttl bucket (early vs late cross)
        for lo,hi,nm in [(30,200,"ttl<200"),(200,600,"200-600"),(600,9999,">600")]:
            rr=[r for r in v if lo<=r["ttl"]<hi]
            if rr: log(f"     {nm}: {agg(rr)}")
        for _ in range(30):
            if not _run: break
            await asyncio.sleep(1)
async def main():
    s=S(); log(f"taker_cross_probe OBSERVE-ONLY THR={THR_BPS}bps (real ASK entry)")
    await asyncio.gather(cb_ws(s),discovery(s),signal_loop(s),reporter(s))
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
