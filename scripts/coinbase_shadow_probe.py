"""coinbase_shadow_probe.py — re-run the fast-strategy shadow test but with the
Coinbase us-east feed (~15ms) instead of Binance Tokyo (~123ms). OBSERVE ONLY.

Signal = buy the side BTC/ETH has already moved toward (vs window open), late in
a 5m/15m up/down window. Records the Polymarket CLOB ask WE'd pay (taker) and, at
settle, our realized EV. Goal: does the 100ms-faster feed flip our_ev from the
prior -1.5% (Binance) toward positive? (no orders, no money)
"""
import asyncio, json, time, signal, sys, datetime
from collections import defaultdict
import httpx
try: import websockets
except ImportError: print("pip install websockets"); sys.exit(1)
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass

ASSETS={"btc":"BTC-USD","eth":"ETH-USD","sol":"SOL-USD","xrp":"XRP-USD","doge":"DOGE-USD"}  # Coinbase us-east (BNB/HYPE not on CB)
PROD2COIN={v:k for k,v in ASSETS.items()}
import math
THR_BPS=2.0; DECISION_TTL=280; MIN_TTL=12     # THR is cheap pre-gate to limit REST
SIGMA_ANN=0.6; MODEL_MARGIN=0.025; YR_SEC=31557600.0   # MODEL direction selection: buy when p_lead-ask>margin
def Phi(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
CB_WS="wss://ws-feed.exchange.coinbase.com"
CB_CANDLES="https://api.exchange.coinbase.com/products/{p}/candles"
GAMMA="https://gamma-api.polymarket.com/markets"
OUTF="data/coinbase_shadow.jsonl"; LOG="data/coinbase_shadow.log"
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
        s.px=defaultdict(lambda:None); s.pxT=defaultdict(lambda:None)
        s.bids=defaultdict(dict); s.asks=defaultdict(dict)   # level2 books (capped)
        s.win={}; s.fired={}; s.stats=defaultdict(int)

def _prune(book, keep, top_high):
    if len(book)<=keep*2: return
    ks=sorted(book)                       # ascending
    drop = ks[:-keep] if top_high else ks[keep:]   # bids keep highest / asks keep lowest
    for p in drop: book.pop(p,None)

async def cb_ws(s):
    d=1
    while _run:
        try:
            async with websockets.connect(CB_WS,ping_interval=15,open_timeout=12,max_size=16*1024*1024) as ws:
                await ws.send(json.dumps({"type":"subscribe","product_ids":list(ASSETS.values()),
                                          "channels":["level2_batch"]}))
                log(f"Coinbase WS connected (level2_batch {list(ASSETS)})"); d=1
                while _run:
                    m=json.loads(await asyncio.wait_for(ws.recv(),timeout=30))
                    t=m.get("type"); c=PROD2COIN.get(m.get("product_id"))
                    if not c: continue
                    if t=="snapshot":
                        s.bids[c]={float(p):float(sz) for p,sz in m.get("bids",[])[:300]}
                        s.asks[c]={float(p):float(sz) for p,sz in m.get("asks",[])[:300]}
                    elif t=="l2update":
                        for ch in m.get("changes",[]):
                            side,p,sz=ch[0],float(ch[1]),float(ch[2])
                            book=s.bids[c] if side=="buy" else s.asks[c]
                            if sz==0: book.pop(p,None)
                            else: book[p]=sz
                        _prune(s.bids[c],300,True); _prune(s.asks[c],300,False)
                    else: continue
                    bb=max(s.bids[c]) if s.bids[c] else None
                    ba=min(s.asks[c]) if s.asks[c] else None
                    if bb and ba and ba>bb:
                        s.px[c]=(bb+ba)/2; s.pxT[c]=now(); s.stats["ticks"]+=1
        except Exception as e:
            if not _run: break
            log(f"cb ws err {str(e)[:50]}"); await asyncio.sleep(d); d=min(30,d*2)

async def cb_open(c, prod, st):
    try:
        iso=lambda t: datetime.datetime.utcfromtimestamp(t).isoformat()
        r=(await c.get(CB_CANDLES.format(p=prod),params={"granularity":60,"start":iso(st),"end":iso(st+60)})).json()
        if isinstance(r,list) and r: return float(sorted(r)[0][3])   # [time,low,high,open,close,vol]
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
                                up=ids[outs.index("Up")]; dn=ids[outs.index("Down")]
                                op=await cb_open(c,prod,st)
                                s.win[slug]={"coin":coin,"prod":prod,"start":st,"settle":settle,
                                             "up":up,"dn":dn,"open":op,"cid":m.get("conditionId")}
                            except: continue
                for slug,w in list(s.win.items()):
                    if w["open"] is None and w["settle"]-now()>0:
                        w["open"]=await cb_open(c,w["prod"],w["start"])
                    if w["settle"]-now()<-150 and slug not in s.fired: del s.win[slug]
        except Exception as e: log(f"disc err {str(e)[:40]}")
        for _ in range(15):
            if not _run: break
            await asyncio.sleep(1)

async def rest_book(tok):
    """return (best_bid, best_ask) for a polymarket token."""
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok})).json()
        asks=sorted((float(a["price"]),float(a["size"])) for a in b.get("asks",[]))
        bids=sorted(((float(a["price"]),float(a["size"])) for a in b.get("bids",[])),reverse=True)
        ba=next((p for p,sz in asks if sz>0 and p<1.0),None)
        bb=next((p for p,sz in bids if sz>0 and p>0.0),None)
        return bb,ba
    except: pass
    return None,None

async def signal_loop(s):
    while _run:
        for slug,w in list(s.win.items()):
            ttl=w["settle"]-now(); px=s.px.get(w["coin"])
            if w["open"] is None or px is None: continue
            if slug not in s.fired and MIN_TTL<=ttl<=DECISION_TTL:
                leadlog=math.log(px/w["open"]); move=leadlog*1e4
                if abs(move)>=THR_BPS:                       # cheap pre-gate
                    v=SIGMA_ANN*math.sqrt(max(ttl,1)/YR_SEC)
                    p_up=Phi(leadlog/v) if v>0 else 0.5
                    side="Up" if p_up>=0.5 else "Down"; p_lead=max(p_up,1-p_up)
                    tok=w["up"] if side=="Up" else w["dn"]
                    bid,ask=await rest_book(tok)
                    if ask is not None:
                        mid=(bid+ask)/2 if bid else ask
                        if (p_lead-mid)>MODEL_MARGIN:        # MODEL edge at mid (reachable by maker bid)
                            age=round((now()-s.pxT[w["coin"]])*1000) if s.pxT[w["coin"]] else None
                            s.fired[slug]={"ttl":int(ttl),"move":round(move,1),"side":side,
                                           "ask":ask,"bid":bid,"fair":round(p_lead,3),
                                           "edge":round(p_lead-ask,3),"feed_age_ms":age,"_f":False}
                            s.stats["fired"]+=1
                            log(f"SIG {slug} ttl={int(ttl)}s {side} p={p_lead:.2f} bid={bid} ask={ask} edge_t=+{round(p_lead-ask,2)}")
            if ttl<-20 and slug in s.fired and not s.fired[slug]["_f"]:
                await finalize(s,slug,w)
        await asyncio.sleep(1)

async def finalize(s,slug,w):
    fe=s.fired[slug]; fe["_f"]=True
    close=s.px.get(w["coin"])
    winner=("Up" if close>=w["open"] else "Down") if (close and w["open"]) else None
    our_win=(winner==fe["side"]) if winner else None
    ev_t=((1.0/fe["ask"]-1.0) if our_win else -1.0) if (our_win is not None and fe["ask"]) else None
    bidp=fe.get("bid")
    maker_px=round(bidp+0.01,2) if bidp else None   # post bid 1 tick up; OPTIMISTIC fill (ignores miss+adverse sel)
    ev_m=((1.0/maker_px-1.0) if our_win else -1.0) if (our_win is not None and maker_px) else None
    row={"slug":slug,"coin":w["coin"],"side":fe["side"],"move_bps":fe["move"],"ttl":fe["ttl"],
         "ask":fe["ask"],"bid":bidp,"maker_px":maker_px,"fair":fe.get("fair"),"edge":fe.get("edge"),
         "feed_age_ms":fe["feed_age_ms"],"winner":winner,"our_win":our_win,
         "our_ev":round(ev_t,3) if ev_t is not None else None,
         "maker_ev":round(ev_m,3) if ev_m is not None else None}
    open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
    s.stats["settled"]+=1
    log(f"SETTLE {slug} win={our_win} ev={row['our_ev']} ask={fe['ask']}")
    del s.win[slug]; del s.fired[slug]

async def reporter(s):
    await asyncio.sleep(20)
    while _run:
        # running EV summary
        evs=[]
        try:
            for ln in open(OUTF,encoding="utf-8"):
                o=json.loads(ln);
                if o.get("our_ev") is not None: evs.append(o["our_ev"])
        except: pass
        agg=f"avg_ev={sum(evs)/len(evs)*100:+.1f}% n={len(evs)}" if evs else "no settles yet"
        log(f"STAT ticks={s.stats['ticks']} windows={len(s.win)} fired={s.stats['fired']} "
            f"settled={s.stats['settled']} | {agg}")
        for _ in range(30):
            if not _run: break
            await asyncio.sleep(1)

async def main():
    s=S(); log(f"coinbase_shadow_probe (Coinbase 15ms feed) OBSERVE-ONLY thr={THR_BPS}bps")
    await asyncio.gather(cb_ws(s),discovery(s),signal_loop(s),reporter(s))

if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
