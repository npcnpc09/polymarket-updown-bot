"""Hourly regime signature: bin DRY btc/eth windows into chronological HOUR buckets, compute our EV per
hour, then characterize BTC's market behavior that hour (realized vol, net directional move, range,
efficiency=trend/chop). Compare PROFITABLE hours vs LOSING hours -> what does the market look like when
we win a lot vs lose a lot. Descriptive diagnostic (user's ask)."""
import json,math,httpx,statistics,datetime
from collections import defaultdict
ROWS=[]
for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if "won" in r and isinstance(r.get("B"),(int,float)) and r.get("coin")in("btc","eth"):
        ROWS.append(r)
def pnl(r): return 5*(1-r["B"]) if r["won"] else -5*r["B"]
sts=[int(r["slug"].split("-")[-1]) for r in ROWS]
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
def fetch(sym,lo,hi):
    out={};cur=lo
    while cur<hi:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[2]),float(x[3]),float(x[4]))  # o,h,l,c
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
BTC=fetch("BTCUSDT",min(sts)-120,max(sts)+360)
def hour_feats(h0):
    mins=[BTC.get(h0+60*i) for i in range(60)]; mins=[m for m in mins if m]
    if len(mins)<30: return None
    closes=[m[3] for m in mins]; opens=mins[0][0]
    rets=[math.log(closes[i]/closes[i-1])*1e4 for i in range(1,len(closes))]
    vol=statistics.pstdev(rets)                       # realized vol bps/min
    net=abs(math.log(closes[-1]/opens)*1e4)           # net directional move bps
    hi=max(m[1] for m in mins); lo=min(m[2] for m in mins)
    rng=math.log(hi/lo)*1e4                            # high-low range bps
    path=sum(abs(x) for x in rets)
    eff=net/path if path>0 else 0                     # efficiency: trend(1) vs chop(0)
    return {"vol":vol,"net":net,"rng":rng,"eff":eff}
# bin by hour
H=defaultdict(list)
for r in ROWS: H[int(int(r["slug"].split("-")[-1])//3600)*3600].append(r)
hours=[]
for h0,rs in H.items():
    if len(rs)<5: continue
    f=hour_feats(h0)
    if not f: continue
    ev=statistics.mean(pnl(r) for r in rs); win=sum(1 for r in rs if r["won"])/len(rs)
    hours.append({"h0":h0,"ev":ev,"win":win,"n":len(rs),**f})
hours.sort(key=lambda x:x["ev"])
print("可用小时桶: %d (每桶>=5窗)\n"%len(hours))
def grp(rs,lbl):
    if not rs: return
    m=lambda k: statistics.mean(r[k] for r in rs)
    print("  %-14s 小时数%-3d 我们EV%+.2f 胜%2.0f%% | BTC: 波动%.1f 净位移%.0f 区间%.0f 效率%.2f"%(
        lbl,len(rs),m("ev"),m("win")*100,m("vol"),m("net"),m("rng"),m("eff")))
n3=len(hours)//3
print("=== 亏损最多 vs 盈利最多 的小时, BTC波动特征 ===")
grp(hours[:n3],"亏损1/3小时")
grp(hours[n3:2*n3],"中间1/3")
grp(hours[2*n3:],"盈利1/3小时")
print("\n=== 相关系数(小时EV vs BTC特征) ===")
for k in ("vol","net","rng","eff"):
    xs=[h[k] for h in hours]; ys=[h["ev"] for h in hours]
    mx=statistics.mean(xs); my=statistics.mean(ys)
    cov=statistics.mean((x-mx)*(y-my) for x,y in zip(xs,ys)); sx=statistics.pstdev(xs); sy=statistics.pstdev(ys)
    print("  EV vs %-5s: %+.3f"%(k,cov/(sx*sy) if sx*sy>0 else 0))
print("\n最亏的5个小时:")
for h in hours[:5]:
    print("  %s EV%+.2f 胜%2.0f%% | 波动%.1f 净%.0f 区间%.0f 效率%.2f"%(datetime.datetime.utcfromtimestamp(h["h0"]).strftime("%m-%d %Hh"),h["ev"],h["win"]*100,h["vol"],h["net"],h["rng"],h["eff"]))
print("最赚的5个小时:")
for h in hours[-5:]:
    print("  %s EV%+.2f 胜%2.0f%% | 波动%.1f 净%.0f 区间%.0f 效率%.2f"%(datetime.datetime.utcfromtimestamp(h["h0"]).strftime("%m-%d %Hh"),h["ev"],h["win"]*100,h["vol"],h["net"],h["rng"],h["eff"]))
