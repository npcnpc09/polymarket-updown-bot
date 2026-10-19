"""maker_paper_real.py — REALISTIC, heavily-instrumented PAPER probe whose purpose is
PITFALL DISCOVERY (not EV confirmation). OBSERVE ONLY, no orders.

Bakes in every fix/finding so far, and logs rich diagnostics per signal so we can mine
for new pitfalls:
  - timing: only fire when window is >=120s old (open finalized -> no phantom-open) AND
    ttl>=45s (avoid ultra-low-ttl where fair0.85 = <10bps lead = oracle-flip zone).
  - phantom detector: record open fetched EARLY (at discovery) vs LATE (>=120s in); flag drift.
  - edge cap: only MARGIN < edge <= EDGE_MAX (huge edge = model error, defer to market).
  - liquidity: skip wide spread (ask-bid > MAX_SPREAD) = thin book.
  - dual fill model (queue realism): touch (ask<=B) vs through (ask<=B-1tick) = fill-rate bracket.
  - ORACLE truth: after settle, read the traded token's CONVERGED market price (=actual
    Chainlink resolution) and compare to our Coinbase close-vs-open call -> flag oracle_flip.
  - adverse selection: WR on filled (touch/through) vs WR on all signals.
Row per settled signal -> data/maker_paper_real.jsonl
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
SIGMA_ANN=0.5; MARGIN=0.04; EDGE_MAX=0.15; YR=31557600.0; THR_BPS=2.0
FAIR_MIN=0.85; MAX_SPREAD=0.06; MIN_WIN_AGE=120; MIN_TTL=45
CB_WS="wss://ws-feed.exchange.coinbase.com"
CB_CANDLES="https://api.exchange.coinbase.com/products/{p}/candles"
GAMMA="https://gamma-api.polymarket.com/markets"
OUTF="data/maker_paper_real.jsonl"; LOG="data/maker_paper_real.log"
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
                                up=ids[outs.index("Up")]; dn=ids[outs.index("Down")]
                                op_e=await cb_open(c,prod,st)   # EARLY open (may be phantom if <120s in)
                                s.win[slug]={"coin":coin,"prod":prod,"dur":du,"start":st,"settle":settle,
                                             "up":up,"dn":dn,"open_e":op_e,"open_l":None}
                            except: continue
                for slug,w in list(s.win.items()):
                    # LATE open: refetch once the window is >=120s old (finalized) -> phantom detector
                    age=now()-w["start"]
                    if w["open_l"] is None and age>=MIN_WIN_AGE and w["settle"]-now()>0:
                        w["open_l"]=await cb_open(c,w["prod"],w["start"])
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
            ttl=w["settle"]-now(); age=now()-w["start"]; px=s.px.get(w["coin"])
            if slug in s.orders or px is None: continue
            if age<MIN_WIN_AGE or ttl<MIN_TTL: continue        # (fix1) no phantom-open / no ultra-low-ttl
            op=w["open_l"] if w["open_l"] is not None else w["open_e"]
            if op is None: continue
            lead=math.log(px/op)
            if abs(lead*1e4)<THR_BPS: continue
            v=SIGMA_ANN*math.sqrt(max(ttl,1)/YR); p_up=Phi(lead/v) if v>0 else 0.5
            side="Up" if p_up>=0.5 else "Down"; p_lead=max(p_up,1-p_up); tok=w["up"] if side=="Up" else w["dn"]
            if p_lead<FAIR_MIN: continue
            bid,ask=await pm_book(tok)
            if bid is None or ask is None: continue
            spread=ask-bid
            if spread>MAX_SPREAD: s.stats["skip_spread"]+=1; continue   # (fix) thin book
            B=round(ask-0.02,2)
            if B<=bid: B=round(bid+0.01,2)
            if not (0.30<=B<=0.95) or B>=ask: continue
            edge=p_lead-B
            if edge<=MARGIN or edge>EDGE_MAX: s.stats["skip_edge"]+=1; continue   # (fix4) edge cap
            phantom=(w["open_e"] is not None and w["open_l"] is not None and
                     abs(w["open_e"]/w["open_l"]-1)>0.0003)   # >3bps early/late open drift
            s.orders[slug]={"coin":w["coin"],"side":side,"B":B,"fair":round(p_lead,3),"edge":round(edge,3),
                "ask":ask,"bid":bid,"spread":round(spread,3),"ttl0":int(ttl),"lead_bps":round(lead*1e4,1),
                "open":op,"tok":tok,"settle":w["settle"],"phantom":phantom,"fire_ts":now(),"confirmed":None,
                "touch":False,"through":False,"conv_px":None,"_done":False,"_lastpoll":0}
            s.stats["fired"]+=1
            log(f"SIG {slug} {side} fair={p_lead:.2f} edge=+{edge:.2f} lead={lead*1e4:.0f}bps spread={spread:.2f} B={B} ttl={int(ttl)}s phantom={phantom}")
        # monitor fills (dual model) until settle, then resolve via market-converged price
        for slug,o in list(s.orders.items()):
            if o["_done"]: continue
            # CONFIRMATION: ~45s after fire, is the signal still fair>=0.85 same side? (filters transient spikes)
            if o["confirmed"] is None and now()-o["fire_ts"]>=45:
                cpx=s.px.get(o["coin"])
                if cpx is not None and o["open"]:
                    cl=math.log(cpx/o["open"]); ct=o["settle"]-now()
                    cv=SIGMA_ANN*math.sqrt(max(ct,1)/YR); cpu=Phi(cl/cv) if cv>0 else 0.5
                    cside="Up" if cpu>=0.5 else "Down"; cfair=max(cpu,1-cpu)
                    o["confirmed"]=bool(cfair>=FAIR_MIN and cside==o["side"])
            if now()-o["_lastpoll"]>3 and o["settle"]-now()>-5:
                o["_lastpoll"]=now()
                bid,ask=await pm_book(o["tok"])
                if ask is not None:
                    if ask<=o["B"] and not o["touch"]:
                        o["touch"]=True; log(f"  TOUCH {slug} ask {ask}<=B {o['B']}")
                    if ask<=round(o["B"]-0.01,2) and not o["through"]:
                        o["through"]=True
                if bid is not None and ask is not None and o["settle"]-now()<75:
                    o["conv_px"]=(bid+ask)/2     # converged mid of our side near settle = actual resolution proxy
            if o["settle"]-now()<-15: await finalize(s,slug,o)
        await asyncio.sleep(1)

async def finalize(s,slug,o):
    o["_done"]=True
    cb_close=s.px.get(o["coin"])
    cb_winner=("Up" if cb_close>=o["open"] else "Down") if (cb_close and o["open"]) else None
    cb_pred_win=(cb_winner==o["side"]) if cb_winner else None
    # ACTUAL resolution = converged market mid of the side we 'bought' captured just before settle
    cp=o.get("conv_px"); actual_win=(cp>=0.5) if cp is not None else None
    oracle_flip=(cb_pred_win is not None and actual_win is not None and cb_pred_win!=actual_win)
    row={"slug":slug,"coin":o["coin"],"side":o["side"],"fair":o["fair"],"edge":o["edge"],
         "lead_bps":o["lead_bps"],"spread":o["spread"],"B":o["B"],"ttl0":o["ttl0"],"phantom":o["phantom"],
         "confirmed":o["confirmed"],
         "touch":o["touch"],"through":o["through"],"conv_px":round(cp,3) if cp is not None else None,
         "cb_pred_win":cb_pred_win,"actual_win":actual_win,"oracle_flip":oracle_flip}
    open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
    s.stats["settled"]+=1
    log(f"DONE {slug} touch={o['touch']} through={o['through']} cb_win={cb_pred_win} actual={actual_win} oracle_flip={oracle_flip}")
    del s.orders[slug]

async def reporter(s):
    await asyncio.sleep(20)
    while _run:
        rows=[]
        try:
            for ln in open(OUTF,encoding="utf-8"): rows.append(json.loads(ln))
        except: pass
        n=len(rows)
        tf=[r for r in rows if r["touch"]]; thr=[r for r in rows if r["through"]]
        def wr(rs,key="actual_win"):
            v=[r for r in rs if r.get(key) is not None]
            return f"{sum(1 for r in v if r[key])/len(v)*100:.0f}%(n{len(v)})" if v else "na"
        flips=sum(1 for r in rows if r.get("oracle_flip"))
        conf=[r for r in rows if r.get("confirmed") is True]; unconf=[r for r in rows if r.get("confirmed") is False]
        log(f"STAT ticks={s.stats['ticks']} win={len(s.win)} fired={s.stats['fired']} settled={n} "
            f"skip(spread={s.stats['skip_spread']},edge={s.stats['skip_edge']}) | "
            f"touch_fill={len(tf)}/{n} | WR_signal={wr(rows)} WR_touch={wr(tf)} | "
            f"CONFIRMED WR={wr(conf)} vs UNCONFIRMED WR={wr(unconf)} | oracle_flips={flips}")
        for _ in range(30):
            if not _run: break
            await asyncio.sleep(1)
async def main():
    s=S(); log(f"maker_paper_real PITFALL-DETECTOR fair>={FAIR_MIN} edge({MARGIN},{EDGE_MAX}] win_age>={MIN_WIN_AGE}s spread<={MAX_SPREAD}")
    await asyncio.gather(cb_ws(s),discovery(s),signal_loop(s),reporter(s))
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
