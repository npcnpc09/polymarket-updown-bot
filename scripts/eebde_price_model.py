"""Reverse-engineer eebde's BETTING PRICE model from his real fills. copy_cum_live.jsonl has his_avgpx
(his avg fill price on the favorite) + leadf (lead at copy) + win per window. Model his_avgpx = f(lead)
and compare to the FAIR price (= actual win rate in that lead bin). If his_avgpx < win_rate, that gap is
his real +EV edge (buys the favorite below its true win prob). Also pull recent per-trade activity for a
finer price-vs-lead curve. Output: a price model to plug into the scale sim (replacing the crude one)."""
import json,math,httpx,statistics
EF=[]
for l in open("data/copy_cum_live.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if isinstance(r.get("his_avgpx"),(int,float)) and isinstance(r.get("leadf"),(int,float)) and "win" in r:
        EF.append(r)
print("有 his_avgpx+leadf+win 的窗口: %d\n"%len(EF))
print("=== 他的成交价 vs 领先 vs 公平价(胜率) ===")
print("  |lead|档    n    他均价his_avgpx   实际胜率(公平价)   他的edge(胜率-付价)")
bands=[(0,8),(8,12),(12,18),(18,25),(25,40),(40,200)]
pts=[]
for lo,hi in bands:
    b=[r for r in EF if lo<=abs(r["leadf"])<hi]
    if not b: continue
    hp=statistics.mean(r["his_avgpx"] for r in b); wr=sum(1 for r in b if r["win"])/len(b)
    edge=wr-hp
    print("  %-3d-%-3d   %-4d   %.3f          %.3f            %+.3f"%(lo,hi,len(b),hp,wr,edge))
    pts.append((statistics.mean(abs(r["leadf"]) for r in b),hp))
# 线性拟合 his_avgpx = a + b*|lead|
if len(pts)>=2:
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    mx=statistics.mean(xs); my=statistics.mean(ys)
    bb=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/sum((x-mx)**2 for x in xs)
    aa=my-bb*mx
    print("\n拟合他的价格模型: his_price ≈ %.3f + %.4f*|lead|  (我之前的粗模型: 0.50+0.016*|lead|)"%(aa,bb))
# 整体
hp=statistics.mean(r["his_avgpx"] for r in EF); wr=sum(1 for r in EF if r["win"])/len(EF)
print("\n整体: 他均价 %.3f, 实际favorite胜率 %.3f → 他每股edge %+.3f (=买在胜率下面%.1f个点)"%(hp,wr,wr-hp,(wr-hp)*100))
print("对比我们: live z-maker均价~0.78, z>=2.5胜率~0.84 → 我们edge ~+0.06")