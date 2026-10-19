"""Would a REGIME GATE (pause the strategy when the market is unfavorable) actually help? Test on REAL settled
trades (early_taker + early_maker, each recorded btc_vol = BTC realized vol at entry). If high-vol / choppy
periods have clearly LOWER win% and net EV, then 'pause when btc_vol high' works. Also test regime PERSISTENCE:
does the recent realized state separate good vs bad windows? This validates the user's adaptive-gate idea
BEFORE building it (predicting single-window reversal failed: macro-trend & chop_score didn't separate; this
tests the different angle of recent-regime state)."""
import json,os,statistics
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T=[]
for fn in ("early_taker_probe.jsonl","early_maker_live.jsonl"):
    fp=os.path.join(ROOT,"data",fn)
    if not os.path.exists(fp): continue
    for l in open(fp,encoding="utf-8"):
        if not l.strip(): continue
        r=json.loads(l)
        if not r.get("live"): continue
        bv=r.get("btc_vol")
        if bv is None: continue
        if r.get("kind")=="entry" and "won" in r and r.get("paid") is not None:
            T.append({"bv":bv,"won":r["won"],"price":r["paid"]})
        elif "n_W" in r and (r.get("winner") or r.get("win")) and r.get("avg_px"):
            T.append({"bv":bv,"won":r["n_W"]>r["n_L"],"price":r["avg_px"]})
print("带btc_vol的真实结算单: %d\n"%len(T))
if len(T)<20: print("样本太少, 先继续攒");
bvs=sorted(t["bv"] for t in T);
def stat(g):
    if not g: return None
    n=len(g); w=sum(1 for t in g if t["won"]); ev=sum((1-t["price"]) if t["won"] else -t["price"] for t in g)/n
    return n,w/n*100,ev,statistics.mean(t["bv"] for t in g)
# split by vol tertiles
q1=bvs[len(bvs)//3]; q2=bvs[2*len(bvs)//3]
print("btc_vol 分位: 低<%.1f / 中 / 高>%.1f\n"%(q1,q2))
print("%-12s %5s %6s %9s %8s"%("regime","n","胜%","净EV/股","均vol"))
for lab,g in (("低vol(平静)",[t for t in T if t["bv"]<q1]),("中vol",[t for t in T if q1<=t["bv"]<q2]),("高vol(震荡?)",[t for t in T if t["bv"]>=q2])):
    s=stat(g)
    if s: print("%-12s %5d %5.0f%% %+8.3f %7.1f"%(lab,s[0],s[1],s[2],s[3]))
print("\n判读: 若 低vol胜率/EV >> 高vol => '高vol暂停'有用, 值得建gate;")
print("若各档差不多 => btc_vol不分regime好坏, gate没用(像macro trend一样被定价). 看方向+留意小样本.")
