"""Backtest the 'mid-price band (0.25-0.5) is UNDERPRICED' hypothesis using ce25's trades as (price,
outcome) samples. Per price band: actual win-rate vs avg price (= market implied prob); edge = win - price
(>0 = underpriced = +EV to buy). Split by HOUR for OOS stability. Caveat: it's ce25's selection (not a
neutral sample) and reconstructed winners (binance, not Chainlink), but it's the broadest (price,outcome)
data we have."""
import httpx,json,math,statistics,time,datetime
from collections import defaultdict
CE="0xcE25E214D5cfE4f459cf67F08DF581885AAE7Fdc"
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
A=[]
for off in range(0,6000,500):
    try: a=c.get("https://data-api.polymarket.com/activity",params={"user":CE,"limit":500,"offset":off}).json()
    except: break
    if not isinstance(a,list) or not a: break
    A+=[x for x in a if x.get("type")=="TRADE" and (x.get("side") or "").upper()=="BUY"]
    if len(a)<500: break
SYM={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT","xrp":"XRPUSDT","doge":"DOGEUSDT"}; DUR={"5m":300,"15m":900}
now=int(time.time())
T=[]
for x in A:
    s=x.get("slug","");parts=s.split("-")
    if "updown" not in s or len(parts)<4: continue
    coin=parts[0];dur=next((d for d in DUR if f"-{d}-" in s),None)
    if coin not in SYM or not dur: continue
    try: st=int(parts[-1])
    except: continue
    if st+DUR[dur]>now-30: continue
    T.append({"coin":coin,"dur":dur,"st":st,"side":x.get("outcome"),"price":x.get("price") or 0,"size":x.get("size") or 0})
print("已结算BUY: %d (跨%.1fh)\n"%(len(T),(max(t['st'] for t in T)-min(t['st'] for t in T))/3600))
need=set(t["coin"] for t in T);KL={}
for coin in need:
    out={};cur=min(t["st"] for t in T if t["coin"]==coin)-120;hi=max(t["st"]+DUR[t["dur"]] for t in T if t["coin"]==coin)+300
    while cur<hi:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[4]))
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    KL[coin]=out
for t in T:
    o=KL[t["coin"]].get(t["st"]);cl=KL[t["coin"]].get(t["st"]+DUR[t["dur"]])
    if o and cl:
        win="Up" if cl[1]>=o[0] else "Down"; t["won"]=(t["side"]==win)
        t["hr"]=datetime.datetime.utcfromtimestamp(t["st"]).strftime("%m-%d %Hh")
    else: t["won"]=None
T=[t for t in T if t["won"] is not None]
BANDS=[(0,0.25,"<0.25"),(0.25,0.4,"0.25-0.4"),(0.4,0.5,"0.4-0.5"),(0.5,0.7,"0.5-0.7"),(0.7,1.01,">=0.7")]
def edge(rs): # win - avg_price (>0=低估), 和 $-ROI
    if not rs: return None
    wr=sum(1 for t in rs if t["won"])/len(rs); ap=statistics.mean(t["price"] for t in rs)
    sp=sum(t["size"]*t["price"] for t in rs); pf=sum((t["size"]*(1-t["price"]) if t["won"] else -t["size"]*t["price"]) for t in rs)
    return (len(rs),wr,ap,wr-ap,pf/sp*100 if sp else 0)
print("=== 各价格档: 实际胜率 vs 价格 = 错价 (全样本) ===")
for lo,hi,l in BANDS:
    e=edge([t for t in T if lo<=t["price"]<hi])
    if e: print("  %-10s n=%-4d 实胜%2.0f%% 均价%.2f 错价%+.0fpp ROI%+5.1f%%"%(l,e[0],e[1]*100,e[2],e[3]*100,e[4]))
print("\n=== 0.25-0.5 档 按小时 OOS (错价稳不稳) ===")
mid=[t for t in T if 0.25<=t["price"]<0.5]
byh=defaultdict(list)
for t in mid: byh[t["hr"]].append(t)
for h in sorted(byh):
    e=edge(byh[h])
    if e and e[0]>=8: print("  %s n=%-3d 实胜%2.0f%% 均价%.2f 错价%+.0fpp ROI%+5.1f%%"%(h,e[0],e[1]*100,e[2],e[3]*100,e[4]))
