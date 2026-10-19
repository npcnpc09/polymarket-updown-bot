"""User idea: at the moment of a STRONG reversal, buy the OPPOSITE direction. Test on real lead paths + real
redeem winners. For each window: find first cross |lead|>=8 toward side A (off1). After off1, scan for a
REVERSAL = lead toward the OPPOSITE side B reaching >=REV (off2<=OFFHI). If reversal found, we'd BUY B at off2.
Question: at settle, does B win (reversal CONTINUES = idea works) or does A recover (reversal was a head-fake)?
Also price context: B's lead at off2 -> price model -> is buying B +EV? Sweep REV (how strong a reversal before
betting). If B wins >> its priced odds -> reversal momentum is real (edge); if ~= priced -> priced-in (no edge)."""
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
OFFHI=240
def run(REV):
    bets=[]  # (won_B, priceB, leadB_at_off2)
    base=0
    for key,v in cache.items():
        path=v["lead"]; win=v["win"]
        # first cross >=8
        off1=None;A=None
        for off in range(5,181,2):
            l=pl(path,off)
            if l is not None and abs(l)>=8: off1=off; A="Up" if l>0 else "Down"; break
        if off1 is None: continue
        base+=1
        sgnA=1 if A=="Up" else -1; B="Down" if A=="Up" else "Up"
        # reversal: lead toward B (=-sgnA*lead) reaches >=REV after off1
        off2=None
        for off in range(off1+2,OFFHI+1,2):
            l=pl(path,off)
            if l is not None and (l*-sgnA)>=REV: off2=off; leadB=l*-sgnA; break
        if off2 is None: continue
        bets.append((B==win,price(leadB),leadB))
    return base,bets
print("基准: %d 个 lead>=8 窗\n"%run(8)[0])
print("=== 反转后买相反方向B (按反转强度REV) ===")
print("%-10s %6s %7s %8s %9s %10s"%("反转阈值","触发n","B胜%","均priceB","B净EV/股","对比:A原本会赢%"))
for REV in (5,8,10,12,15):
    base,bets=run(REV)
    if not bets: continue
    n=len(bets); wB=sum(1 for b in bets if b[0])
    ev=sum((1-b[1]) if b[0] else -b[1] for b in bets)/n
    print("B lead>=%-3d %6d %6.0f%% %7.3f %+8.3f %9.0f%%"%(REV,n,wB/n*100,sum(b[1] for b in bets)/n,ev,(n-wB)/n*100))
print("\n判读: 'B胜%' = 反转后买B的真实胜率. 'B净EV/股'用价格模型(反转时B已是favorite, 价已涨).")
print("若 B净EV/股 明显>0 => 反转有动量、买相反方向赚钱(真信号); 若<=0 => 反转方向也priced-in, 没edge.")
print("注意: 'A原本会赢%'>0 说明很多'反转'是假摔A又弹回(=买B反而输).")
