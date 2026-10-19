"""ONE-WEEK backtest (pure binance, downloadable, no Polymarket needed) of the hourly regime signature:
reconstruct OUR win/loss per 5m window (leading side @150s persists to close?), bin by HOUR, and test
whether the hour's BTC EFFICIENCY (trend vs chop) / VOLATILITY explains our hourly win rate. 7 days =
much more robust than 2.5. Metric = WIN RATE (leading-side persistence); no B needed (we lack a week of
PM prices), and win rate is what the regime drives (reversals)."""
import math,httpx,statistics,datetime,time
from collections import defaultdict
NOW=int(time.time()); LO=NOW-7*86400-300; HI=NOW
c=httpx.Client(timeout=30,headers={"User-Agent":"Mozilla/5.0"})
def fetch(sym):
    out={};cur=LO
    while cur<HI:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":HI*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[2]),float(x[3]),float(x[4]))
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
PX={"btc":fetch("BTCUSDT"),"eth":fetch("ETHUSDT")}
print("币安分钟: btc=%d eth=%d (跨%.1f天)\n"%(len(PX["btc"]),len(PX["eth"]),(HI-LO)/86400))
def o(cn,t):
    v=PX[cn].get(t); return v[0] if v else None
# reconstruct windows
wins=[]   # (st, coin, won, |lead|)
for st in range(int(LO//300)*300, HI-300, 300):
    for cn in ("btc","eth"):
        op=o(cn,st); p120=o(cn,st+120); p180=o(cn,st+180); cl=o(cn,st+300)
        if None in (op,p120,p180,cl): continue
        lead=(math.log(p120/op)+math.log(p180/op))/2*1e4
        if abs(lead)<8: continue                      # our cushion filter
        side_up=lead>=0; won=(side_up and cl>=op) or ((not side_up) and cl<op)
        wins.append((st,cn,won,abs(lead)))
print("重建窗口(|lead|>=8): %d, 整体胜率 %.0f%%\n"%(len(wins),sum(1 for w in wins if w[2])/len(wins)*100))
# hourly BTC features
def hfeat(h0):
    mins=[PX["btc"].get(h0+60*i) for i in range(60)]; mins=[m for m in mins if m]
    if len(mins)<30: return None
    cl=[m[3] for m in mins]; op=mins[0][0]
    rets=[math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))]
    vol=statistics.pstdev(rets); net=abs(math.log(cl[-1]/op)*1e4)
    hi=max(m[1] for m in mins); lo=min(m[2] for m in mins); rng=math.log(hi/lo)*1e4
    path=sum(abs(x) for x in rets); eff=net/path if path>0 else 0
    return {"vol":vol,"net":net,"rng":rng,"eff":eff}
H=defaultdict(list)
for st,cn,won,ld in wins: H[int(st//3600)*3600].append(won)
hours=[]
for h0,ws in H.items():
    if len(ws)<6: continue
    f=hfeat(h0)
    if not f: continue
    hours.append({"h0":h0,"win":sum(1 for w in ws if w)/len(ws),"n":len(ws),**f})
hours.sort(key=lambda x:x["win"])
print("可用小时桶: %d\n"%len(hours))
n3=len(hours)//3
def grp(rs,lbl):
    m=lambda k: statistics.mean(r[k] for r in rs)
    print("  %-14s 小时%-3d 我们胜%2.0f%% | BTC 波动%.1f 净位移%.0f 区间%.0f 效率%.3f"%(lbl,len(rs),m("win")*100,m("vol"),m("net"),m("rng"),m("eff")))
print("=== 我们胜率 最低1/3 vs 最高1/3 的小时, BTC特征 ===")
grp(hours[:n3],"低胜率小时"); grp(hours[n3:2*n3],"中间"); grp(hours[2*n3:],"高胜率小时")
print("\n=== 相关系数(小时胜率 vs BTC特征) ===")
for k in ("vol","net","rng","eff"):
    xs=[h[k] for h in hours]; ys=[h["win"] for h in hours]
    mx=statistics.mean(xs); my=statistics.mean(ys)
    cov=statistics.mean((x-mx)*(y-my) for x,y in zip(xs,ys)); sx=statistics.pstdev(xs); sy=statistics.pstdev(ys)
    print("  胜率 vs %-5s: %+.3f"%(k,cov/(sx*sy) if sx*sy>0 else 0))
# 效率分档胜率(窗口级,大样本)
print("\n=== 窗口级: 按所在小时BTC效率分档的胜率 ===")
hf={h["h0"]:h for h in hours}
wf=[(w,hf[int(w[0]//3600)*3600]) for w in wins if int(w[0]//3600)*3600 in hf]
for lo,hi,lbl in ((0,0.08,"效率<0.08 震荡"),(0.08,0.15,"0.08-0.15"),(0.15,0.25,"0.15-0.25"),(0.25,1,"效率>0.25 强趋势")):
    b=[w for w,h in wf if lo<=h["eff"]<hi]
    if b: print("  %-16s n=%-4d 胜%2.0f%%"%(lbl,len(b),sum(1 for w in b if w[2])/len(b)*100))
