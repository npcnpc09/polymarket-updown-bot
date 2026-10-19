"""Win% / EV by accel bucket across ALL DRY history with an accel label. Tests whether accel>0 is too
lax (does win%/EV rise with accel, and where does it turn +EV?). Descriptive — read monotonicity, not
a single bucket. Splits: all-coins vs btc/eth, and with/without cushion(|lead|>=8)."""
import json,statistics
R=[]
for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if "won" not in r or not isinstance(r.get("B"),(int,float)): continue
    if not isinstance(r.get("accel"),(int,float)): continue
    R.append(r)
BK=[(-1e9,0,"<=0"),(0,5,"0-5"),(5,10,"5-10"),(10,15,"10-15"),(15,20,"15-20"),(20,1e9,"20+")]
def report(rs,title):
    print("\n========== %s  (n=%d) =========="%(title,len(rs)))
    print("  accel档    n    胜率   EV     总PnL   累计胜率(>=该档)")
    # precompute cumulative from high to low
    for lo,hi,lbl in BK:
        b=[r for r in rs if lo< r["accel"]<=hi] if lo!=-1e9 else [r for r in rs if r["accel"]<=hi]
        if not b: print("  %-8s   0"%lbl); continue
        w=sum(1 for r in b if r["won"]); ev=sum((5*(1-r["B"]) if r["won"] else -5*r["B"]) for r in b)/len(b)
        pnl=sum((5*(1-r["B"]) if r["won"] else -5*r["B"]) for r in b)
        # cumulative: all with accel > lo (i.e., raising the floor to lo)
        cum=[r for r in rs if r["accel"]>lo]
        cw=sum(1 for r in cum if r["won"])/len(cum)*100 if cum else 0
        cev=sum((5*(1-r["B"]) if r["won"] else -5*r["B"]) for r in cum)/len(cum) if cum else 0
        print("  %-8s %4d  %3.0f%%  %+5.2f  %+6.1f   >%-3.0f: 胜%2.0f%% EV%+.2f n=%d"%(lbl,len(b),w/len(b)*100,ev,pnl,lo if lo!=-1e9 else 0,cw,cev,len(cum)))
report(R,"全部(所有币, 有accel标签的)")
be=[r for r in R if r.get("coin")in("btc","eth")]
report(be,"btc/eth")
cush=[r for r in be if abs(r.get("lead",0)or 0)>=8 and (r.get("max_lead")or 0)>=15]
report(cush,"btc/eth + cushion(|lead|>=8 & maxL>=15) = 自营条件")
