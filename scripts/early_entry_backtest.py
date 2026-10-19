"""Historical backtest: EARLY (30-60s, z>=2.5) vs LATE (165s, z>=2.5) entry. Win rates reconstructed
from binance (robust); entry PRICE from the lowbid-probe's REAL measured timing->price curve (at-bid:
30-60s≈0.682, 165s≈0.767) — empirical, not a guessed model. Compare win% + EV, incl. the both-triggered
subset (clean A/B on same windows)."""
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
def px_at(cn,t):
    lo=(t//60)*60; hi=lo+60; a=PX[cn].get(lo); b=PX[cn].get(hi)
    if a is None: return None
    if b is None: return a
    f=(t-lo)/60.0; return a*(1-f)+b*f
# real measured at-bid prices by entry time (from early_lowbid_probe, 152 win)
PX_EARLY=0.682   # 30-60s
PX_LATE =0.767   # ~165s
rows=[]
for st in range(int(LO//300)*300, NOW-300, 300):
    for cn in ("btc","eth"):
        o=px_at(cn,st); clo=px_at(cn,st+300)
        if o is None or clo is None: continue
        c2=[PX[cn].get(st-60*i) for i in range(31)]; c2=[x for x in c2 if x]
        if len(c2)<20: continue
        vol=statistics.pstdev([math.log(c2[i]/c2[i-1])*1e4 for i in range(1,len(c2))])
        if vol<=0: continue
        def zside(sec):
            p=px_at(cn,st+sec)
            if p is None: return None,None
            lead=math.log(p/o)*1e4; return (abs(lead)/vol), (1 if lead>=0 else -1)
        # EARLY: first of 30/45/60 with z>=2.5
        e=None
        for sec in (30,45,60):
            z,sd=zside(sec)
            if z is not None and z>=2.5: e=sd; break
        # LATE: at 165s
        lz,lsd=zside(165)
        la=lsd if (lz is not None and lz>=2.5) else None
        cwin = 1 if clo>=o else -1   # up wins?
        rows.append({"early":e,"ewin":(e==cwin) if e else None,"late":la,"lwin":(la==cwin) if la else None})
def ev(winrate,price): return winrate*(1-price)-(1-winrate)*price
E=[r for r in rows if r["early"] is not None]; L=[r for r in rows if r["late"] is not None]
ew=sum(1 for r in E if r["ewin"])/len(E) if E else 0
lw=sum(1 for r in L if r["lwin"])/len(L) if L else 0
print("一周窗口: %d\n"%len(rows))
print("=== 各自触发的全部窗口 ===")
print("  EARLY(30-60s z>=2.5): n=%-4d 胜%.0f%% 进价%.3f → EV %+.3f/股"%(len(E),ew*100,PX_EARLY,ev(ew,PX_EARLY)))
print("  LATE (165s   z>=2.5): n=%-4d 胜%.0f%% 进价%.3f → EV %+.3f/股"%(len(L),lw*100,PX_LATE,ev(lw,PX_LATE)))
# both-triggered subset (clean A/B)
B=[r for r in rows if r["early"] is not None and r["late"] is not None]
if B:
    bew=sum(1 for r in B if r["ewin"])/len(B); blw=sum(1 for r in B if r["lwin"])/len(B)
    print("\n=== 同时触发的窗口 (干净A/B, n=%d) ==="%len(B))
    print("  同一批窗口: EARLY胜%.0f%% EV%+.3f | LATE胜%.0f%% EV%+.3f"%(bew*100,ev(bew,PX_EARLY),blw*100,ev(blw,PX_LATE)))
    same=sum(1 for r in B if r["early"]==r["late"]); print("  其中early/late同方向: %d/%d (%.0f%%)"%(same,len(B),same/len(B)*100))
print("\n注: 胜率=币安重建(真); 价格=lowbid probe真实盘口测的时点经验值; EV是两者结合, 价格部分是真实测量不是臆造。")