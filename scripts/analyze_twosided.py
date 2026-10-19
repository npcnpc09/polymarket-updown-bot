"""Analyze twosided.jsonl — TWO-SIDED maker bucketed by EX-ANTE CHOP PREDICTOR. The key question: can we
predict chop at entry and run two-sided ONLY in predicted-chop windows (=+EV)? Uses only v2 rows (have
chop_score/flips). For the deep tiers (mid-4c, mid-6c), split windows by predictor (chop_score>=THRESH or
flips>=2 = predicted CHOP) and show both-fill% + net EV per bucket. If predicted-chop is +EV and
predicted-trend is −EV, the conditional strategy works; if the predictor doesn't separate EV, it doesn't."""
import json,os,statistics
from collections import defaultdict
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
f=os.path.join(ROOT,"data","twosided.jsonl")
rows=[json.loads(l) for l in open(f,encoding="utf-8")] if os.path.exists(f) else []
rows=[r for r in rows if r.get("chop_score") is not None]  # v2 only
if not rows: print("还没v2数据(带chop预测器); 让它跑几个窗 (~5min/窗)"); raise SystemExit
nwin=len(set(r["slug"] for r in rows))
print("v2窗口 %d (带chop预测器)\n"%nwin)
CS_THRESH=2.5  # chop_score>=2.5 => predicted CHOP
def ev(rs): return statistics.mean(r["pnl"] for r in rs) if rs else 0
def bothpct(rs): return sum(1 for r in rs if r["both"])/len(rs)*100 if rs else 0
for tier in (0.04,0.06):
    g=[r for r in rows if r["tier"]==tier]
    if not g: continue
    print("=== 档 mid-%dc ==="%int(tier*100))
    print("  全部:        n=%-3d 两边成交%2.0f%% 净EV%+.3f"%(len(g),bothpct(g),ev(g)))
    chop=[r for r in g if r["chop_score"]>=CS_THRESH]; tr=[r for r in g if r["chop_score"]<CS_THRESH]
    print("  预判震荡(cs>=%.1f): n=%-3d 两边成交%2.0f%% 净EV\033[1m%+.3f\033[0m %s"%(CS_THRESH,len(chop),bothpct(chop),ev(chop),"<-应为正" if chop else ""))
    print("  预判趋势(cs<%.1f):  n=%-3d 两边成交%2.0f%% 净EV%+.3f %s"%(CS_THRESH,len(tr),bothpct(tr),ev(tr),"<-应为负" if tr else ""))
    fchop=[r for r in g if r["flips"]>=2]; ftr=[r for r in g if r["flips"]<2]
    print("  flips>=2(震荡):  n=%-3d 两边成交%2.0f%% 净EV%+.3f"%(len(fchop),bothpct(fchop),ev(fchop)))
    print("  flips<2(趋势):   n=%-3d 两边成交%2.0f%% 净EV%+.3f"%(len(ftr),bothpct(ftr),ev(ftr)))
    print()
print("判读: 若 预判震荡桶净EV>0 而 预判趋势桶净EV<0 => chop可预测 => '只在预判震荡时开两边maker'=+EV(有戏)")
print("若两桶净EV都负/预测器不分离 => 震荡不可事先判 => 又被定价吃掉, 两边maker无条件版确认无路.")
print("(passive=成交上限, 真实更差; 需足够窗数, 早期看方向)")
