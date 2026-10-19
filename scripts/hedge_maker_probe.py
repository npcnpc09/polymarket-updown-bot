"""hedge_maker_probe.py — OBSERVE-ONLY. Replicate eebde's HEDGED maker: rest gentle bids on
BOTH Up and Down, refresh SLOWLY (no aggressive per-tick chasing), accumulate both sides,
hold to settle. Hypothesis (from eebde's real data: ~+1-2% in ALL regimes incl chop): the
both-sides base prevents the choppy-window blowup that killed the aggressive leader-chase
(-60% in chop). Compare ROI by regime (leader-flips) to the aggressive version.
Row -> data/hedge_maker.jsonl
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
THR_BPS=2.0; MIN_TTL=12; REFRESH=12; MAX_FILLS_SIDE=15; YR=31557600.0
CB_WS="wss://ws-feed.exchange.coinbase.com"
CB_CANDLES="https://api.exchange.coinbase.com/products/{p}/candles"
GAMMA="https://gamma-api.polymarket.com/markets"
OUTF="data/hedge_maker.jsonl"; LOG="data/hedge_maker.log"
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
        s.win={}; s.pos={}; s.stats=defaultdict(int)
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
                    if w["settle"]-now()<-200 and slug not in s.pos: del s.win[slug]
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
            if w["open"] is None or px is None: continue
            lead=math.log(px/w["open"])*1e4
            side="Up" if lead>=0 else "Down"
            if slug not in s.pos:
                if abs(lead)<THR_BPS or ttl<MIN_TTL: continue
                s.pos[slug]={"coin":w["coin"],"settle":w["settle"],"up":w["up"],"dn":w["dn"],
                    "start":w["start"],"dur":w["dur"],"fills":[],"restU":None,"restD":None,"convU":None,"_cvp":0,
                    "flips":0,"early_flips":0,"last_side":side,"max_lead":abs(lead),"_done":False,"_lp":0}
                s.stats["opened"]+=1
            o=s.pos[slug]
            if o["_done"]: continue
            if side!=o["last_side"]:
                o["flips"]+=1
                if (now()-o["start"])/o["dur"]<0.5: o["early_flips"]+=1
                o["last_side"]=side
            if abs(lead)>o["max_lead"]: o["max_lead"]=abs(lead)
            if now()-o["_lp"]<REFRESH: continue                  # SLOW refresh (no per-tick chase)
            o["_lp"]=now()
            for which,tok,rk in (("Up",w["up"],"restU"),("Down",w["dn"],"restD")):
                bid,ask=await pm_book(tok)
                if bid is None or ask is None: continue
                nfill=sum(1 for f in o["fills"] if f["side"]==which)
                if o[rk] is not None and ask<=o[rk] and nfill<MAX_FILLS_SIDE:
                    o["fills"].append({"side":which,"price":o[rk]}); s.stats["fills"]+=1
                nb=round(bid+0.01,2)
                o[rk]=nb if nb<ask else bid
        for slug,o in list(s.pos.items()):
            if o["_done"]: continue
            tset=o["settle"]-now()
            if -5<tset<90 and now()-o["_cvp"]>4:
                o["_cvp"]=now(); bU,aU=await pm_book(o["up"])
                if bU is not None and aU is not None: o["convU"]=(bU+aU)/2
            if tset<-15: await finalize(s,slug,o)
        await asyncio.sleep(1)
async def finalize(s,slug,o):
    o["_done"]=True; cU=o.get("convU"); up_win=(cU>=0.5) if cU is not None else None
    if up_win is None: s.stats["unresolved"]+=1; del s.pos[slug]; return
    pnl=cost=0.0; nU=nD=nW=nL=0
    for f in o["fills"]:
        won=(up_win and f["side"]=="Up") or ((not up_win) and f["side"]=="Down")
        cost+=f["price"]; pnl+=(1.0-f["price"]) if won else (-f["price"])
        if f["side"]=="Up": nU+=1
        else: nD+=1
        if won: nW+=1
        else: nL+=1
    avgpx=cost/len(o["fills"]) if o["fills"] else None
    row={"slug":slug,"coin":o["coin"],"n_fills":len(o["fills"]),"n_Up":nU,"n_Down":nD,"n_W":nW,"n_L":nL,
         "avg_fill_px":round(avgpx,3) if avgpx else None,"cost":round(cost,2),"pnl":round(pnl,3),
         "roi":round(pnl/cost*100,1) if cost>0 else None,"up_win":up_win,
         "flips":o["flips"],"early_flips":o["early_flips"],"max_lead":round(o["max_lead"],1)}
    open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
    s.stats["settled"]+=1
    log(f"DONE {slug} fills={len(o['fills'])} (U{nU}/D{nD} W{nW}/L{nL}) avg={row['avg_fill_px']} pnl={row['pnl']} roi={row['roi']}% flips={o['flips']}")
    del s.pos[slug]
async def reporter(s):
    await asyncio.sleep(20)
    while _run:
        rows=[]
        try:
            for ln in open(OUTF,encoding="utf-8"): rows.append(json.loads(ln))
        except: pass
        f=[r for r in rows if r.get("cost",0)>0]
        if f:
            tp=sum(r["pnl"] for r in f); tc=sum(r["cost"] for r in f); tf=sum(r["n_fills"] for r in f)
            avgpx=sum((r["avg_fill_px"] or 0)*r["n_fills"] for r in f)/max(tf,1)
            ch=[r for r in f if r["flips"]>=3]; tr=[r for r in f if r["flips"]<3]
            chroi=sum(r["pnl"] for r in ch)/sum(r["cost"] for r in ch)*100 if ch else float('nan')
            trroi=sum(r["pnl"] for r in tr)/sum(r["cost"] for r in tr)*100 if tr else float('nan')
            log(f"STAT ticks={s.stats['ticks']} opened={s.stats['opened']} fills={s.stats['fills']} settled={len(f)} | "
                f"avg_px={avgpx:.2f} PnL=${tp:+.1f} on ${tc:.0f} ROI={tp/tc*100:+.1f}% | "
                f"trend(flips<3)={trroi:+.0f}%(n{len(tr)}) chop(flips>=3)={chroi:+.0f}%(n{len(ch)})")
        else:
            log(f"STAT ticks={s.stats['ticks']} opened={s.stats['opened']} fills={s.stats['fills']} settled=0")
        for _ in range(30):
            if not _run: break
            await asyncio.sleep(1)
async def main():
    s=S(); log(f"hedge_maker_probe OBSERVE-ONLY both-sides gentle maker, slow refresh {REFRESH}s, hold to settle")
    await asyncio.gather(cb_ws(s),discovery(s),signal_loop(s),reporter(s))
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
