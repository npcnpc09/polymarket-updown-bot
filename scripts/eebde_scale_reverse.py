"""Reverse-engineer eebde's strategy at SCALE ($10k, no tiny-wallet limit) in paper. Over 1 week of
btc/eth 5m windows, simulate STRICT eebde-style continuous loading (add only while lead is strong +
strengthening + clean; stop on wobble) so heavy positions self-select to the strong-clean profile.
ROBUST outputs (outcomes+lead only): does heavy-position win-rate reach ~97%? regime-proof by vol?
diversification = aggregate equity-curve drawdown across all concurrent windows. PnL shown under 2 price
assumptions (efficient vs maker -5c) since we lack real PM prices."""
import math,httpx,statistics,time
NOW=int(time.time()); LO=NOW-7*86400-300
c=httpx.Client(timeout=30,headers={"User-Agent":"Mozilla/5.0"})
def fetch(sym):
    out={};cur=LO
    while cur<NOW:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":NOW*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=float(x[1])
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
PX={"btc":fetch("BTCUSDT"),"eth":fetch("ETHUSDT")}
def px_at(cn,t):  # interpolate minute klines
    lo=(t//60)*60; hi=lo+60; a=PX[cn].get(lo); b=PX[cn].get(hi)
    if a is None: return None
    if b is None: return a
    f=(t-lo)/60.0; return a*(1-f)+b*f
def pmodel(lead): return min(0.95,max(0.50,0.603+0.006*abs(lead)))   # eebde's REAL price model (reverse-engineered from his_avgpx)
ADD_MIN=8; RETRACE=3
wins=[]   # per window: units, avgpx, won, vol, st
for st in range(int(LO//300)*300, NOW-300, 300):
    for cn in ("btc","eth"):
        o=px_at(cn,st); cl=px_at(cn,st+300)
        if o is None or cl is None: continue
        l60=px_at(cn,st+60)
        if l60 is None: continue
        side=1 if l60>=o else -1
        best=-99; units=0; cost=0.0; still=True
        for sec in (30,60,90,120,150,180,210,240):
            p=px_at(cn,st+sec)
            if p is None: continue
            ld=math.log(p/o)*1e4*side
            if still and ld>=ADD_MIN and ld>=best-RETRACE:
                units+=1; cost+=pmodel(ld)
            elif ld<best-RETRACE: still=False
            best=max(best,ld)
        if units==0: continue
        c2=[PX[cn].get(st-60*i) for i in range(31)]; c2=[x for x in c2 if x]
        if len(c2)<20: continue
        vol=statistics.pstdev([math.log(c2[i]/c2[i-1])*1e4 for i in range(1,len(c2))])
        won=(side>0 and cl>=o) or (side<0 and cl<o)
        wins.append({"st":st,"units":units,"avgpx":cost/units,"won":won,"vol":vol})
print("一周加仓窗口: %d\n"%len(wins))
# 1) 重仓胜率(逆向97%?)
print("=== 1) 按仓位(units)分档的胜率 — 重仓能否逼近97% ===")
for lo,hi,lbl in ((1,3,"轻 units1-2"),(3,5,"中 units3-4"),(5,7,"重 units5-6"),(7,99,"超重 units7-8")):
    b=[w for w in wins if lo<=w["units"]<hi]
    if b: print("  %-14s n=%-4d 胜%2.0f%% 均价%.2f 均vol%.1f"%(lbl,len(b),sum(1 for w in b if w["won"])/len(b)*100,statistics.mean(w["avgpx"] for w in b),statistics.mean(w["vol"] for w in b)))
# 2) 重仓(units>=5) regime-proof?
print("\n=== 2) 重仓(units>=5) 按波动 — regime-proof? ===")
hv=[w for w in wins if w["units"]>=5]
for lo,hi,lbl in ((0,8,"平静<8"),(8,12,"8-12"),(12,99,"高>=12")):
    b=[w for w in hv if lo<=w["vol"]<hi]
    if b: print("  %s n=%-3d 胜%2.0f%%"%(lbl,len(b),sum(1 for w in b if w["won"])/len(b)*100))
# 3) 分散: $10k按conviction(units)铺到所有窗口, equity曲线回撤
print("\n=== 3) 分散效果: $10k value-weighted 铺所有窗口 (按时间, 看回撤) ===")
totu=sum(w["units"] for w in wins); dollar_per_unit=10000.0/ (totu/ (len(set(w['st'] for w in wins)) or 1) * 3)  # 粗略: 控制并发敞口
# 简化: 每unit固定$ = 10000 / (并发峰值*单窗最大units) 量级; 这里用每unit $20做shares等价, 重点看曲线形状
DPU=20.0
for pxadj,plbl in ((0.0,"efficient(price=模型)"),(-0.05,"maker -5c"),(-0.10,"maker -10c")):
    wins.sort(key=lambda x:x["st"]); cum=0;peak=0;maxdd=0
    for w in wins:
        eff=max(0.01,w["avgpx"]+pxadj)
        p=w["units"]*DPU*((1-eff) if w["won"] else -eff)
        cum+=p; peak=max(peak,cum); maxdd=min(maxdd,cum-peak)
    print("  %-22s 总PnL$%+8.0f 最大回撤$%+8.0f (回撤/盈利=%.0f%%)"%(plbl,cum,maxdd,abs(maxdd)/cum*100 if cum>0 else 0))
print("\n注: PnL绝对值依赖价格假设(我们无真PM价); 重点看(1)重仓胜率能否逼近97%(2)是否regime-proof(3)分散后回撤占比。")