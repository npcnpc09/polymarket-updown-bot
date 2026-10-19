"""Test the regime-timing idea: does DRY's RECENT (lagged, past-only) performance predict the NEXT
window's performance? If yes (regime persists/autocorrelated), 'go live only when DRY is hot' is +EV.
If next-window outcome is independent of recent (no autocorrelation), it's chasing noise (the $113->$90
trap: regime flips with no warning). Strictly no lookahead: rolling metric uses windows BEFORE current."""
import json,statistics
R=[]
for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if "won" in r and isinstance(r.get("B"),(int,float)) and r.get("coin")in("btc","eth"):
        try: st=int(r["slug"].split("-")[-1])
        except: continue
        r["_st"]=st; R.append(r)
R.sort(key=lambda x:x["_st"])
def pnl(r): return 5*(1-r["B"]) if r["won"] else -5*r["B"]
N=24  # rolling window (lagged)
rows=[]
for i in range(len(R)):
    past=R[max(0,i-N):i]
    if len(past)<N: continue
    rev=[p for p in past]
    rwin=sum(1 for p in rev if p["won"])/len(rev)
    rev_ev=statistics.mean(pnl(p) for p in rev)
    rows.append({"cur":R[i],"rwin":rwin,"rev_ev":rev_ev})
print("可用样本(有滞后窗口): %d  (滚动N=%d, 仅用过去)\n"%(len(rows),N))
def summ(rs,lbl):
    if not rs: print("  %-26s n=0"%lbl); return
    w=sum(1 for d in rs if d["cur"]["won"]); ev=statistics.mean(pnl(d["cur"]) for d in rs)
    print("  %-26s n=%-4d 当前窗 胜%2.0f%% EV%+.2f"%(lbl,len(rs),w/len(rs)*100,ev))
print("=== 按近期(滞后)EV 分,看\"下一窗\"表现 ===")
summ([d for d in rows if d["rev_ev"]>0.05],"近期EV>+0.05 (热)")
summ([d for d in rows if -0.05<=d["rev_ev"]<=0.05],"近期EV ~0 (中性)")
summ([d for d in rows if d["rev_ev"]<-0.05],"近期EV<-0.05 (冷)")
print("\n=== 按近期(滞后)胜率分位 ===")
rws=sorted(d["rwin"] for d in rows); t1=rws[len(rws)//3]; t2=rws[2*len(rws)//3]
summ([d for d in rows if d["rwin"]>=t2],"近期胜率 高1/3")
summ([d for d in rows if t1<=d["rwin"]<t2],"近期胜率 中1/3")
summ([d for d in rows if d["rwin"]<t1],"近期胜率 低1/3")
# 相关系数
import math
xs=[d["rev_ev"] for d in rows]; ys=[pnl(d["cur"]) for d in rows]
mx=statistics.mean(xs); my=statistics.mean(ys)
cov=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/len(xs)
sx=statistics.pstdev(xs); sy=statistics.pstdev(ys)
corr=cov/(sx*sy) if sx>0 and sy>0 else 0
print("\n近期EV 与 下一窗EV 的相关系数: %+.3f  (接近0=无持续性=无法择时)"%corr)
# baseline
print("\n基线(全部当前窗): 胜%.0f%% EV%+.2f"%(sum(1 for d in rows if d["cur"]["won"])/len(rows)*100,statistics.mean(pnl(d["cur"]) for d in rows)))
