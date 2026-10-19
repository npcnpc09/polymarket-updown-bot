"""Two-way self-taker vs eebde monitor:
 A) eebde HEAVY (>=1500) but WE skip -> which of our filters blocked (why we didn't).
 B) WE trade (DRY passing self-taker filters max_lead>=15 & |lead|>=8) but eebde LIGHT/skip -> his
    final_cum + OUR outcome. Does his light-bet correctly flag windows WE lose? (= why he didn't, and
    whether we should defer to his sizing)."""
import json,re,httpx,math,datetime
from collections import defaultdict
# eebde favorite + final_cum per slug
EF={}
for fn in ("data/copy_cum_live.jsonl","data/copy_cum.jsonl"):
    try:
        for l in open(fn,encoding="utf-8"):
            l=l.strip()
            if not l: continue
            try: r=json.loads(l)
            except: continue
            if r.get("slug") and r.get("side"): EF[r["slug"]]={"fav":r["side"],"final":r.get("final_cum",0)}
    except FileNotFoundError: pass
# OUR DRY entries passing self-taker filters
OUR={}
for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if r.get("coin") in ("btc","eth") and "won" in r and "-5m-" in r.get("slug","") and isinstance(r.get("B"),(int,float)):
        if (r.get("max_lead")or 0)>=15 and abs(r.get("lead",0) or 0)>=8:
            OUR[r["slug"]]=r
print("=== 方向B: 我们做了(自营过滤通过), 他做没做 + 我们输赢 ===")
both=[s for s in OUR if s in EF]
print("我们自营会下的窗口: %d, 其中eebde有数据: %d\n"%(len(OUR),len(both)))
def wr(rs): return sum(1 for s in rs if OUR[s]["won"])/len(rs)*100 if rs else 0
def ev(rs): return sum((5*(1-OUR[s]["B"]) if OUR[s]["won"] else -5*OUR[s]["B"]) for s in rs)/len(rs) if rs else 0
heavy=[s for s in both if EF[s]["final"]>=1500]
light=[s for s in both if EF[s]["final"]<1500]
print("  他也重注(>=1500): n=%-3d 我们胜%2.0f%% EV%+.2f"%(len(heavy),wr(heavy),ev(heavy)))
print("  他轻注/没重注(<1500): n=%-3d 我们胜%2.0f%% EV%+.2f  <- 他'没做'是否预警了我们的亏?"%(len(light),wr(light),ev(light)))
# 方向不一致(我们下了但他favorite是反向=他根本没押我们这侧)
opp=[s for s in both if OUR[s]["side"]!=EF[s]["fav"]]
if opp:
    print("\n  我们押的方向他favorite是反的: n=%d 我们胜%2.0f%% EV%+.2f  <- 他押反我们=他认为我们错"%(len(opp),wr(opp),ev(opp)))
# 逐小时: 我们下了他轻注的占比 + 我们在那些上的胜率
print("\n=== 逐小时: 我们做了但他轻注(<1500)的 ===")
byh=defaultdict(list)
for s in light: byh[datetime.datetime.utcfromtimestamp(int(s.split("-")[-1])).strftime("%H")].append(s)
for hr in sorted(byh):
    rs=byh[hr]; print("  %sh: %d个(我们做他轻注), 我们胜%2.0f%%"%(hr,len(rs),wr(rs)))
