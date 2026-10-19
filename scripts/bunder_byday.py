"""OOS check of 'B<0.40 deep-underdog loses': split by DAY. If B<0.40 loses consistently each day = robust;
if only one day = regime artifact (overfit). btc/eth DRY, all + cushion(self-taker) cuts."""
import json,datetime
from collections import defaultdict
R=[]
for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if "won" in r and isinstance(r.get("B"),(int,float)) and r.get("coin")in("btc","eth"):
        try: st=int(r["slug"].split("-")[-1])
        except: continue
        r["_day"]=datetime.datetime.utcfromtimestamp(st).strftime("%m-%d"); R.append(r)
def stat(rs):
    if not rs: return "n=0"
    w=sum(1 for r in rs if r["won"]); ev=sum((5*(1-r["B"]) if r["won"] else -5*r["B"]) for r in rs)/len(rs)
    pnl=sum((5*(1-r["B"]) if r["won"] else -5*r["B"]) for r in rs)
    return "n=%-3d 胜%2.0f%% EV%+.2f 总$%+.1f"%(len(rs),w/len(rs)*100,ev,pnl)
days=sorted(set(r["_day"] for r in R))
def block(pool,title):
    print("\n=== %s ==="%title)
    print("  %-7s | %-34s | %-34s"%("日","B<0.40 (买深劣势)","B>=0.40"))
    for d in days:
        dd=[r for r in pool if r["_day"]==d]
        under=[r for r in dd if r["B"]<0.40]; rest=[r for r in dd if r["B"]>=0.40]
        print("  %-7s | %-34s | %-34s"%(d,stat(under),stat(rest)))
    allu=[r for r in pool if r["B"]<0.40]
    print("  %-7s | %-34s | %-34s"%("合计",stat(allu),stat([r for r in pool if r["B"]>=0.40])))
block(R,"btc/eth 全部")
cu=[r for r in R if abs(r.get("lead",0)or 0)>=8 and (r.get("max_lead")or 0)>=15]
block(cu,"btc/eth + cushion(自营条件)")
# 细分: B<0.40里再看深浅
print("\n=== B<0.40 内部细分(全部btc/eth) ===")
for lo,hi,lbl in ((0,0.25,"B<0.25"),(0.25,0.33,"B0.25-0.33"),(0.33,0.40,"B0.33-0.40")):
    print("  %-12s %s"%(lbl,stat([r for r in R if lo<=r["B"]<hi])))
