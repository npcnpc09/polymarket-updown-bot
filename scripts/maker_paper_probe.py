"""maker_paper_probe.py — paper-test MAKER execution of the model-edge directional
strategy. OBSERVE ONLY (no real orders). When the model finds edge on a side,
register a hypothetical maker bid at best_bid+1tick (if price < fair-margin);
then monitor the Polymarket book and mark FILLED if the ask drops to our bid.
Measures: fill-rate, WR on filled vs WR on all signals (adverse selection), and
realized maker EV on filled positions. Coinbase 15ms level2 feed for signal.
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
SIGMA_ANN=0.5; MARGIN=0.04; YR=31557600.0; THR_BPS=2.0; DECISION_TTL=280; MIN_TTL=20
FAIR_MIN=0.80   # only fire on high-confidence direction (model reliable ~81-91% there)
CB_WS="wss://ws-feed.exchange.coinbase.com"
CB_CANDLES="https://api.exchange.coinbase.com/products/{p}/candles"
GAMMA="https://gamma-api.polymarket.com/markets"
OUTF="data/maker_paper.jsonl"; LOG="data/maker_paper.log"
def Phi(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
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
        s.bids=defaultdict(dict); s.asks=defaultdict(dict)
        s.win={}; s.orders={}; s.stats=defaultdict(int)

def _prune(book,keep,hi):
    if len(book)<=keep*2: return
    ks=sorted(book); drop=ks[:-keep] if hi else ks[keep:]
    for p in drop: book.pop(p,None)

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
                    if bb and ba and ba>bb: s.px[c]=(bb+ba)/2; s.pxT[c]=now(); s.stats["ticks"]+=1
        except Exception as e:
            if not _run: break
            log(f"cb err {str(e)[:40]}"); await asyncio.sleep(d); d=min(30,d*2)

async def cb_open(c,prod,st):
    try:
        iso=lambda t: datetime.datetime.utcfromtimestamp(t).isoformat()
        r=(await c.get(CB_CANDLES.format(p=prod),params={"granularity":60,"start":iso(st-180),"end":iso(st+120)})).json()
        if isinstance(r,list) and r:
            for cd in r:
                if int(cd[0])==st: return float(cd[3])    # [time,low,high,OPEN,close,vol]
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
                    if w["settle"]-now()<-160 and slug not in s.orders: del s.win[slug]
        except Exception as e: log(f"disc {str(e)[:30]}")
        for _ in range(15):
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
            if w["open"] is None or px is None or slug in s.orders: continue
            if MIN_TTL<=ttl<=DECISION_TTL:
                lead=math.log(px/w["open"]);
                if abs(lead*1e4)<THR_BPS: continue
                v=SIGMA_ANN*math.sqrt(max(ttl,1)/YR); p_up=Phi(lead/v) if v>0 else 0.5
                side="Up" if p_up>=0.5 else "Down"; p_lead=max(p_up,1-p_up); tok=w["up"] if side=="Up" else w["dn"]
                if p_lead<FAIR_MIN: continue             # (2) only high-confidence direction
                bid,ask=await pm_book(tok)
                if bid is None or ask is None: continue
                B=round(ask-0.02,2)                       # (3) TIGHT maker bid: 2c below ask -> only tight fills, avoid deep adverse
                if B<=bid: B=round(bid+0.01,2)            # but stay a resting maker above best bid
                if not (0.30<=B<=0.90) or B>=ask: continue
                if (p_lead-B)>MARGIN:                     # edge at our maker bid
                    s.orders[slug]={"coin":w["coin"],"side":side,"B":B,"fair":round(p_lead,3),
                        "sig_ask":ask,"post_ts":now(),"settle":w["settle"],"open":w["open"],
                        "filled":False,"fill_ts":None,"_done":False}
                    s.stats["fired"]+=1
                    log(f"BID {slug} {side} p={p_lead:.2f} bid@{B} (ask={ask}) edge=+{p_lead-B:.2f}")
        # monitor fills
        for slug,o in list(s.orders.items()):
            if o["_done"]: continue
            if not o["filled"] and now()-o.get("_lastpoll",0)>3:
                o["_lastpoll"]=now(); w=s.win.get(slug)
                if w:
                    tok=w["up"] if o["side"]=="Up" else w["dn"]
                    _,ask=await pm_book(tok)
                    if ask is not None and ask<=o["B"]:    # market came to our bid -> filled
                        o["filled"]=True; o["fill_ts"]=now()
                        log(f"  FILL {slug} {o['side']}@{o['B']} (ask hit {ask})")
            if o["settle"]-now()<-20: await finalize(s,slug,o)
        await asyncio.sleep(1)

async def finalize(s,slug,o):
    o["_done"]=True; w=s.win.get(slug,{}); close=s.px.get(o["coin"])
    winner=("Up" if close>=o["open"] else "Down") if (close and o["open"]) else None
    sig_win=(winner==o["side"]) if winner else None
    ev=None; filled_win=None
    if o["filled"] and sig_win is not None:
        filled_win=sig_win; ev=(1.0/o["B"]-1.0) if filled_win else -1.0
    row={"slug":slug,"coin":o["coin"],"side":o["side"],"fair":o["fair"],"bid":o["B"],
         "sig_ask":o["sig_ask"],"filled":o["filled"],"sig_win":sig_win,
         "filled_win":filled_win,"maker_ev":round(ev,3) if ev is not None else None}
    open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
    s.stats["settled"]+=1
    if o["filled"]: s.stats["filled"]+=1
    log(f"DONE {slug} filled={o['filled']} sig_win={sig_win} ev={row['maker_ev']}")
    del s.orders[slug]

async def reporter(s):
    await asyncio.sleep(20)
    while _run:
        rows=[]
        try:
            for ln in open(OUTF,encoding="utf-8"): rows.append(json.loads(ln))
        except: pass
        nf=[r for r in rows if r["filled"] and r["maker_ev"] is not None]
        allsig=[r for r in rows if r["sig_win"] is not None]
        fr=f"{len(nf)}/{len(rows)} filled" if rows else "0"
        ev=f"{sum(r['maker_ev'] for r in nf)/len(nf)*100:+.1f}%" if nf else "na"
        wf=f"{sum(1 for r in nf if r['filled_win'])/len(nf)*100:.0f}%" if nf else "na"
        ws=f"{sum(1 for r in allsig if r['sig_win'])/len(allsig)*100:.0f}%" if allsig else "na"
        opens=sum(1 for w in s.win.values() if w.get("open") is not None)
        pxc=sum(1 for c in ASSETS if s.px.get(c) is not None)
        log(f"STAT ticks={s.stats['ticks']} win={len(s.win)} opens={opens} px={pxc} fired={s.stats['fired']} {fr} | EV={ev} WR_f={wf} WR_sig={ws}")
        for _ in range(30):
            if not _run: break
            await asyncio.sleep(1)

async def main():
    s=S(); log(f"maker_paper_probe OBSERVE-ONLY margin={MARGIN} sigma={SIGMA_ANN}")
    await asyncio.gather(cb_ws(s),discovery(s),signal_loop(s),reporter(s))
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
