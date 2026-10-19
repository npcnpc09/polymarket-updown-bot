"""Backtest the SIGNAL quality of the confirmed-strengthening maker filter at different thresholds, BEFORE
loosening the live probe. Reliable part (lead path + real redeem outcome): how many windows qualify, and does
the strengthening favorite still WIN at a high rate. (The maker FILL behavior is NOT backtestable reliably —
that's the live probe's job; here we validate the signal + sample-rate tradeoff.) Compare STRONG/GROW configs:
for each, scan checkpoints [60,90,120,150] for lead>=STRONG AND growing (>=+GROW vs 30s ago, same side); record
the strengthening side + win. Report n, win%, and edge = win% - price-implied (price model at that lead)."""
import json,os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cache=json.load(open(os.path.join(ROOT,"data","lead_paths.json")))
PTS=[(0,0.52),(2,0.57),(5,0.72),(8,0.79),(11,0.867),(15,0.89),(20,0.913),(30,0.94),(50,0.95)]
def price(lead):
    lead=abs(lead)
    if lead<=PTS[0][0]: return PTS[0][1]
    for i in range(1,len(PTS)):
        if lead<=PTS[i][0]:
            (x0,y0),(x1,y1)=PTS[i-1],PTS[i]; return y0+(y1-y0)*(lead-x0)/(x1-x0)
    return PTS[-1][1]
def pl(path,off):
    for o in range(off,off+6):
        if str(o) in path: return path[str(o)]
    return None
CPS=[60,90,120,150]
def run(STRONG,GROW):
    picks=[]  # (won, lead_at_qual)
    for key,v in cache.items():
        path=v["lead"]; win=v["win"]; hist={}
        for cp in CPS:
            l=pl(path,cp)
            if l is None: continue
            hist[cp]=l; prev=hist.get(cp-30)
            if abs(l)<STRONG: continue
            if prev is None or (l>=0)!=(prev>=0) or abs(l)<abs(prev)+GROW: continue
            side="Up" if l>0 else "Down"
            picks.append((side==win,abs(l))); break   # first qualifying checkpoint per window
    return picks
print("缓存窗口 %d\n"%len(cache))
print("%-18s %6s %6s %8s %9s %9s"%("配置","合格窗","胜%","均lead","价隐含%","错价pp"))
for STRONG,GROW in ((10,3),(8,2),(8,3),(10,2),(12,3)):
    p=run(STRONG,GROW)
    if not p: continue
    n=len(p); w=sum(1 for x in p if x[0]); avgl=sum(x[1] for x in p)/n
    pimp=sum(price(x[1]) for x in p)/n
    tag=" ←现在" if (STRONG,GROW)==(10,3) else (" ←放宽目标" if (STRONG,GROW)==(8,2) else "")
    print("STRONG%2d/GROW%d   %6d %5.0f%% %7.1f %7.0f%% %+7.0f%s"%(STRONG,GROW,n,w/n*100,avgl,pimp*100,(w/n-pimp)*100,tag))
print("\n判读: '胜%'=走强favorite真胜率(可靠); '错价pp'=胜%−价隐含>0 => 走强持仓被低估(maker便宜接=+EV的来源).")
print("放宽(8/2)若 合格窗明显增多 且 胜%/错价 没怎么降 => 放宽安全, 加速live验证. (fill仍要live探针定)")
