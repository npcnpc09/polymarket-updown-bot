"""Regime guard (monitor + signal, NOT yet auto-gating maker). Continuously computes rolling DRY
performance (btc/eth settled) over a fast(12) and slow(24) window -> regime STATE:
  COLD     (rolling win<0.68 or EV<-0.05)  -> maker_ok=False (pause: cold regimes persist, forward EV -0.17)
  GOOD     (win>=0.73 and EV>0)            -> favorable=True (market suits our load-favorite strategy)
  NEUTRAL  (between)                        -> maker_ok=True, favorable=False (default-on; maker's cheap
                                              entry makes neutral still +EV)
maker_ok = (state != COLD). Writes data/regime_state.json (current) + data/regime_log.jsonl (transitions)
for FORWARD validation before we wire it into the maker. Thresholds from scripts/regime_persistence.py
(2.5-day, in-sample) -> validate that COLD-flagged periods really underperform before trusting."""
import json,time,statistics,os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRY=os.path.join(ROOT,"data","multi_window_engine.jsonl")
STATE=os.path.join(ROOT,"data","regime_state.json")
LOG=os.path.join(ROOT,"data","regime_log.jsonl")
N_FAST=12; N_SLOW=24
WIN_COLD=0.68; WIN_GOOD=0.73; EV_COLD=-0.05
def pnl(r): return 5*(1-r["B"]) if r["won"] else -5*r["B"]
def load_recent(k):
    R=[]
    try:
        for l in open(DRY,encoding="utf-8"):
            l=l.strip()
            if not l: continue
            try: r=json.loads(l)
            except: continue
            if "won" in r and isinstance(r.get("B"),(int,float)) and r.get("coin")in("btc","eth"):
                try: r["_st"]=int(r["slug"].split("-")[-1])
                except: continue
                R.append(r)
    except FileNotFoundError: return []
    R.sort(key=lambda x:x["_st"])
    return R[-k:]
def metrics(rs):
    if not rs: return None,None
    return sum(1 for r in rs if r["won"])/len(rs), statistics.mean(pnl(r) for r in rs)
def maker_loss_streak():
    """Consecutive losing windows at the end of the MAKER's OWN ledger, counting only RECENT (<12min)
    windows so a stale pre-stop streak doesn't immediately re-stop a freshly restarted maker. Used as the
    STOP signal (the maker's real PnL), since DRY 'warm' != maker winning (maker bids weaker/earlier)."""
    rows=[]
    try:
        for l in open(os.path.join(ROOT,"data","early_maker_live.jsonl"),encoding="utf-8"):
            l=l.strip()
            if not l: continue
            try: r=json.loads(l)
            except: continue
            try: st=int(r["slug"].split("-")[-1])
            except: continue
            if st>=int(time.time())-720 and isinstance(r.get("pnl"),(int,float)): rows.append((st,r["pnl"]))
    except FileNotFoundError: return 0
    rows.sort()
    s=0
    for st,p in reversed(rows):
        if p>0: break
        s+=1
    return s
def run():
    last_state=None
    while True:
        try:
            R=load_recent(N_SLOW)
            if len(R)>=N_FAST:
                wf,ef=metrics(R[-N_FAST:]); ws,es=metrics(R)
                if ws<WIN_COLD or es<EV_COLD: state="COLD"
                elif ws>=WIN_GOOD and es>0: state="GOOD"
                else: state="NEUTRAL"
                maker_ok=(state!="COLD"); favorable=(state=="GOOD")
                streak=0                                    # consecutive losses at the most-recent end (streaky: loss->more loss)
                for r in reversed(R):
                    if r["won"]: break
                    streak+=1
                wstreak=0                                    # consecutive WINS at the end (>=2 = warming, next-window EV +0.15)
                for r in reversed(R):
                    if not r["won"]: break
                    wstreak+=1
                mls=maker_loss_streak()                      # maker's OWN recent loss streak (STOP signal)
                rec={"ts":int(time.time()),"state":state,"maker_ok":maker_ok,"favorable":favorable,
                     "win_fast":round(wf,3),"ev_fast":round(ef,3),"win_slow":round(ws,3),"ev_slow":round(es,3),
                     "loss_streak":streak,"win_streak":wstreak,"maker_loss_streak":mls,"n":len(R),"last_st":R[-1]["_st"]}
                json.dump(rec,open(STATE,"w"))
                if state!=last_state:
                    open(LOG,"a",encoding="utf-8").write(json.dumps(rec)+"\n")
                    print("[regime] -> %s  win_slow=%.2f ev_slow=%+.2f maker_ok=%s"%(state,ws,es,maker_ok),flush=True)
                    last_state=state
        except Exception as e:
            print("err",repr(e)[:120],flush=True)
        time.sleep(60)
if __name__=="__main__": run()
