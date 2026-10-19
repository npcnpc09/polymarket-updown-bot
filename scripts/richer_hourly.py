"""Beyond volatility: characterize each hour with MULTIPLE market-structure features and see which
actually explains our hourly DRY EV — not just vol. New dimensions: return AUTOCORRELATION (trend vs
mean-revert), net DIRECTIONAL move, efficiency. Specifically profile the $59->$113 profitable run hours
(06-04 18:00 ~ 06-05 11:00) vs the rest. Answers: what ELSE was going on that vol missed."""
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
c=httpx.Client(timeout=30,headers={"User-Agent":"Mozilla/5.0"})
def fetch(sym,lo,hi):
    out={};cur=lo
    while cur<hi:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=float(x[4])
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
BTC=fetch("BTCUSDT",min(sts)-3600,max(sts)+360)
def autocorr(xs,lag=1):
    if len(xs)<lag+3: return 0
    a=xs[:-lag]; b=xs[lag:]; ma=statistics.mean(a); mb=statistics.mean(b)
    cov=sum((x-ma)*(y-mb) for x,y in zip(a,b)); va=sum((x-ma)**2 for x in a); vb=sum((y-mb)**2 for y in b)
    return cov/math.sqrt(va*vb) if va>0 and vb>0 else 0
def hfeat(h0):
    cl=[BTC.get(h0+60*i) for i in range(61)]; cl=[x for x in cl if x]
    if len(cl)<40: return None
    r1=[math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))]            # 1-min returns
    r5=[math.log(cl[i]/cl[i-5])*1e4 for i in range(5,len(cl),5)]          # 5-min returns
    vol=statistics.pstdev(r1); net=abs(math.log(cl[-1]/cl[0])*1e4)
    path=sum(abs(x) for x in r1); eff=net/path if path>0 else 0
    return {"vol":vol,"net":net,"eff":eff,"ac1":autocorr(r1,1),"ac5":autocorr(r5,1)}
H=defaultdict(list)
for r in ROWS: H[int(int(r["slug"].split("-")[-1])//3600)*3600].append(r)
hours=[]
for h0,rs in H.items():
    if len(rs)<5: continue
    f=hfeat(h0)
    if not f: continue
    hours.append({"h0":h0,"ev":statistics.mean(pnl(r) for r in rs),"win":sum(1 for r in rs if r["won"])/len(rs),"n":len(rs),**f})
print("小时桶: %d\n"%len(hours))
print("=== 各特征 与 我们小时EV 的相关系数 ===")
for k in ("vol","net","eff","ac1","ac5"):
    xs=[h[k] for h in hours]; ys=[h["ev"] for h in hours]
    mx=statistics.mean(xs); my=statistics.mean(ys)
    cov=statistics.mean((x-mx)*(y-my) for x,y in zip(xs,ys)); sx=statistics.pstdev(xs); sy=statistics.pstdev(ys)
    print("  EV vs %-4s : %+.3f"%(k,cov/(sx*sy) if sx*sy>0 else 0))
# 盈利run时段 vs 其他
run_lo=int(datetime.datetime(2026,6,4,18,0,tzinfo=datetime.timezone.utc).timestamp())
run_hi=int(datetime.datetime(2026,6,5,11,30,tzinfo=datetime.timezone.utc).timestamp())
run=[h for h in hours if run_lo<=h["h0"]<run_hi]; rest=[h for h in hours if not(run_lo<=h["h0"]<run_hi)]
def prof(rs,lbl):
    m=lambda k: statistics.mean(r[k] for r in rs)
    print("  %-18s 小时%-3d EV%+.2f 胜%2.0f%% | 波动%.1f 净位移%.0f 效率%.2f 自相关1m%+.2f 5m%+.2f"%(lbl,len(rs),m("ev"),m("win")*100,m("vol"),m("net"),m("eff"),m("ac1"),m("ac5")))
print("\n=== $59->$113 盈利run时段 vs 其他 ===")
prof(run,"盈利run(6/4晚-6/5午)"); prof(rest,"其他时段")
print("\n=== 最赚10小时 的特征画像 ===")
for h in sorted(hours,key=lambda x:-x["ev"])[:10]:
    print("  %s EV%+.2f 胜%2.0f%% | 波动%.1f 净%.0f 效率%.2f ac1%+.2f ac5%+.2f"%(datetime.datetime.utcfromtimestamp(h["h0"]).strftime("%m-%d %Hh"),h["ev"],h["win"]*100,h["vol"],h["net"],h["eff"],h["ac1"],h["ac5"]))
