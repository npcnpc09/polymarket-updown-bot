"""winner_skew_maker.py — OBSERVE-ONLY. Develop the missing skill: WINNER-SKEWED bid
management. Post a bid on the leading side, but GATE fills on the underlying (Coinbase):
a fill only 'counts' if at that instant the underlying STILL strongly leads our side
(>= STRONG_BPS) and isn't fading. That models pulling the bid the moment the underlying
turns -> our fills land on PULLBACKS in a confirmed trend (winners), not REVERSALS (losers).
Compare winner% / ROI to the naive dip-catch (63% winner, -8.6%). Log regime features.
Row -> data/winner_skew.jsonl
"""
import asyncio, json, time, signal, sys, math, datetime
from collections import defaultdict, deque
import httpx
try: import websockets
except ImportError: print("pip install websockets"); sys.exit(1)
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
ASSETS={"btc":"BTC-USD","eth":"ETH-USD","sol":"SOL-USD","xrp":"XRP-USD","doge":"DOGE-USD"}
PROD2COIN={v:k for k,v in ASSETS.items()}
ENTER_BPS=8.0; STRONG_BPS=6.0; MIN_TTL=12; MAX_FILLS=40; YR=31557600.0
import statistics
GATE_K=1.8     # gate opens only when |lead| >= GATE_K * ATR(lead noise) -> signal>>noise
CANCEL_K=1.0   # pull bid when lead retraces from peak by > CANCEL_K * ATR (ATR trailing stop)
STOP_CONFIRM_SECS=10.0  # confirmed signal-stop: reversal must persist this long before we 'sell'
CB_WS="wss://ws-feed.exchange.coinbase.com"; CB_CANDLES="https://api.exchange.coinbase.com/products/{p}/candles"
GAMMA="https://gamma-api.polymarket.com/markets"
OUTF="data/winner_skew.jsonl"; LOG="data/winner_skew.log"
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
        s.leadhist=defaultdict(lambda:deque(maxlen=8))  # recent leads per coin
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
            s.leadhist[w["coin"]].append(lead)
            side="Up" if lead>=0 else "Down"
            if slug not in s.pos:
                if abs(lead)<ENTER_BPS or ttl<MIN_TTL: continue
                s.pos[slug]={"coin":w["coin"],"side":side,"settle":w["settle"],"up":w["up"],"dn":w["dn"],
                    "start":w["start"],"dur":w["dur"],"fills":[],"restB":None,"convU":None,"_cvp":0,
                    "flips":0,"early_flips":0,"last_side":side,"max_lead":abs(lead),"strong_since":None,
                    "leadbuf":deque(maxlen=30),"peak_lead":abs(lead),"_done":False,"_lp":0,
                    "stop_px":{"Up":None,"Down":None},"stop_px_conf":{"Up":None,"Down":None},
                    "rev_since":{"Up":None,"Down":None}}
                s.stats["opened"]+=1
            o=s.pos[slug]
            if o["_done"]: continue
            if side!=o["last_side"]:
                o["flips"]+=1
                if (now()-o["start"])/o["dur"]<0.5: o["early_flips"]+=1
                o["last_side"]=side
            if abs(lead)>o["max_lead"]: o["max_lead"]=abs(lead)
            if now()-o["_lp"]<2: continue
            o["_lp"]=now()
            # WINNER-SKEW GATE (ATR-DYNAMIC): gate opens when |lead| beats BOTH a floor AND
            # GATE_K*ATR (signal>>its own noise); pulled when lead retraces from peak by CANCEL_K*ATR.
            o["leadbuf"].append(lead)
            lb=list(o["leadbuf"]); same=(lead>=0)==(side=="Up")
            if same and abs(lead)>o["peak_lead"]: o["peak_lead"]=abs(lead)
            # CHOPPINESS = how often the lead's INCREMENTS flip direction (noise, not trend)
            if len(lb)>=8:
                diffs=[lb[i]-lb[i-1] for i in range(1,len(lb))]
                dch=sum(1 for i in range(1,len(diffs)) if (diffs[i]>0)!=(diffs[i-1]>0))
                choppy = dch > len(diffs)*0.45
                # ATR (increment noise) for the trailing stop
                atr = statistics.pstdev(diffs)*2.0 if len(diffs)>=4 else 3.0
            else:
                choppy=True; atr=3.0
            signal_ok = same and abs(lead)>=STRONG_BPS and not choppy
            retraced = same and abs(lead) < o["peak_lead"] - max(CANCEL_K*atr, 4.0)
            # persistence still required (don't fill the first confirming tick)
            if signal_ok and not retraced:
                if o["strong_since"] is None: o["strong_since"]=now()
            else:
                o["strong_since"]=None
            strong = o["strong_since"] is not None and (now()-o["strong_since"])>=15.0
            fading = retraced
            o["side"]=side
            if not same: o["peak_lead"]=abs(lead)   # leader flipped -> reset peak to new side
            tok=w["up"] if side=="Up" else w["dn"]
            bid,ask=await pm_book(tok)
            if bid is None or ask is None: continue
            # only hold a live bid when underlying confirms; else 'pulled' (no fill possible)
            if strong and not fading:
                if o["restB"] is not None and ask<=o["restB"] and len(o["fills"])<MAX_FILLS:
                    o["fills"].append({"side":side,"price":o["restB"],"lead":round(lead,1)}); s.stats["fills"]+=1
                nb=round(bid+0.01,2); o["restB"]=nb if nb<ask else bid
            else:
                o["restB"]=None   # pulled
            # SIGNAL-STOP modeling: two variants, captured per held side as the SELL price (PM bid).
            #  naive (stop_px)      = first tick the underlying reverses against us (whipsaws on noise)
            #  confirmed (stop_px_conf) = reversal must PERSIST >= STOP_CONFIRM_SECS (filters tick noise)
            for hs in set(f["side"] for f in o["fills"]):
                if side!=hs:                      # underlying currently against side hs
                    if o["rev_since"][hs] is None: o["rev_since"][hs]=now()
                    if o["stop_px"][hs] is None:   # naive: grab immediately
                        stok=w["up"] if hs=="Up" else w["dn"]
                        sb,_sa=await pm_book(stok)
                        if sb is not None: o["stop_px"][hs]=sb
                    if o["stop_px_conf"][hs] is None and (now()-o["rev_since"][hs])>=STOP_CONFIRM_SECS:
                        stok=w["up"] if hs=="Up" else w["dn"]
                        sb,_sa=await pm_book(stok)
                        if sb is not None: o["stop_px_conf"][hs]=sb
                else:
                    o["rev_since"][hs]=None         # back on our side -> reversal was noise, reset
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
    pnl=cost=0.0; nW=nL=0; pnl_ss=0.0; pnl_ssc=0.0; n_stopped=0; n_stopped_c=0; n_up=0; n_dn=0
    for f in o["fills"]:
        if f["side"]=="Up": n_up+=1
        else: n_dn+=1
        won=(up_win and f["side"]=="Up") or ((not up_win) and f["side"]=="Down")
        cost+=f["price"]; pnl+=(1.0-f["price"]) if won else (-f["price"])
        if won: nW+=1
        else: nL+=1
        sp=o["stop_px"].get(f["side"])
        if sp is not None: pnl_ss+=(sp-f["price"]); n_stopped+=1   # naive: sold at first reversal
        else: pnl_ss+=(1.0-f["price"]) if won else (-f["price"])  # never reversed -> held
        spc=o["stop_px_conf"].get(f["side"])
        if spc is not None: pnl_ssc+=(spc-f["price"]); n_stopped_c+=1   # confirmed: sold at persistent reversal
        else: pnl_ssc+=(1.0-f["price"]) if won else (-f["price"])      # no persistent reversal -> held
    avgpx=cost/len(o["fills"]) if o["fills"] else None
    row={"slug":slug,"coin":o["coin"],"n_fills":len(o["fills"]),"n_W":nW,"n_L":nL,
         "avg_fill_px":round(avgpx,3) if avgpx else None,"cost":round(cost,2),"pnl":round(pnl,3),
         "pnl_sstop":round(pnl_ss,3),"n_stopped":n_stopped,
         "pnl_sstop_conf":round(pnl_ssc,3),"n_stopped_conf":n_stopped_c,
         "roi":round(pnl/cost*100,1) if cost>0 else None,"flips":o["flips"],"early_flips":o["early_flips"],"max_lead":round(o["max_lead"],1),
         "up_win":bool(up_win),"n_up":n_up,"n_dn":n_dn}
    open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
    s.stats["settled"]+=1
    if o["fills"]: log(f"DONE {slug} fills={len(o['fills'])} (W{nW}/L{nL}) avg={row['avg_fill_px']} roi={row['roi']}% flips={o['flips']}")
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
            tW=sum(r["n_W"] for r in f); tL=sum(r["n_L"] for r in f)
            avgpx=sum((r["avg_fill_px"] or 0)*r["n_fills"] for r in f)/max(tf,1)
            ss=[r for r in f if "pnl_sstop" in r]
            ssmsg=""
            if ss:
                sc=sum(r["cost"] for r in ss); hh=sum(r['pnl'] for r in ss)
                sp=sum(r["pnl_sstop"] for r in ss); spc=sum(r.get("pnl_sstop_conf",r["pnl"]) for r in ss)
                ssmsg=(f" | n={len(ss)} hold={hh/sc*100:+.1f}% naiveStop={sp/sc*100:+.1f}% "
                       f"confStop={spc/sc*100:+.1f}%")
            log(f"STAT ticks={s.stats['ticks']} opened={s.stats['opened']} fills={s.stats['fills']} settled={len(f)} | "
                f"total_fills={tf} winner%={tW/max(tW+tL,1)*100:.0f} (vs naive 63%) avg_px={avgpx:.2f} | ROI={tp/tc*100:+.1f}% (vs naive -8.6%){ssmsg}")
        else:
            log(f"STAT ticks={s.stats['ticks']} opened={s.stats['opened']} fills={s.stats['fills']} settled=0")
        for _ in range(30):
            if not _run: break
            await asyncio.sleep(1)
async def main():
    s=S(); log(f"winner_skew_maker OBSERVE-ONLY: bid on leader, GATE fills on underlying still-strongly-leading (skew to winners)")
    await asyncio.gather(cb_ws(s),discovery(s),signal_loop(s),reporter(s))
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
