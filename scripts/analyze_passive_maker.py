"""Analyze passive_maker.jsonl — the fill-ratio-vs-discount curve. Per tier (mid-0/2/4/6c): fill% (how often
price came down to our hypothetical bid), win% OF FILLED (adverse selection check), avg fill price, and
EV=mean(won?1-price:-price) over FILLED probes. Compare to eebde's +0.08/share. Deeper tier should show
lower fill% AND lower win% (you only fill when the favorite weakens) — that's the maker adverse-selection tax,
measured on real data, no money. Upper-bound (front-of-queue assumption)."""
import json,os,statistics
from collections import defaultdict
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
f=os.path.join(ROOT,"data","passive_maker.jsonl")
rows=[json.loads(l) for l in open(f,encoding="utf-8")] if os.path.exists(f) else []
if not rows: print("还没数据 (5m窗结算需~5分钟; 让它跑一会)"); raise SystemExit
nwin=len(set(r["slug"] for r in rows)); nprobe=len(set((r["slug"],r["cp"]) for r in rows))
print("窗口 %d | lead>=5探测点 %d | 每点4档 (mid-0/2/4/6c)\n"%(nwin,nprobe))
byt=defaultdict(list)
for r in rows: byt[r["tier"]].append(r)
print("%-8s %6s %7s %8s %8s %9s"%("折扣档","总点","成交%","成交胜%","均成交价","EV/股"))
for d in (0.0,0.02,0.04,0.06):
    g=byt.get(d,[]);
    if not g: continue
    fl=[r for r in g if r["filled"]]
    fr=len(fl)/len(g)*100
    if fl:
        wp=sum(1 for r in fl if r["won"])/len(fl)*100
        avgp=statistics.mean(r["bid"] for r in fl)
        ev=statistics.mean((1-r["bid"]) if r["won"] else -r["bid"] for r in fl)
        print("mid-%-3dc %6d %6.0f%% %7.0f%% %8.3f %+8.3f"%(int(d*100),len(g),fr,wp,avgp,ev))
    else:
        print("mid-%-3dc %6d %6.0f%% %7s %8s %9s"%(int(d*100),len(g),fr,"—","—","—"))
print("\nEV/股>0 = maker在该档+EV (对比eebde +0.080). 成交%随档加深下降=越深越难成交;")
print("成交胜%随档加深下降=逆向选择(只在favorite衰退时成交). 两者夹击=maker抓不到eebde的便宜.")
print("注: 被动=假设排队最前 -> 成交%是上限; 真实更低. 若上限都-EV, 是便宜的kill信号.")
