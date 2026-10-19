"""Where does ce25 put his MONEY? By price band: trade count, total $ invested (size*price = his real
exposure), avg bet size, win%, profit, ROI, and % of his total $. Identifies his 重注区 (where the dollars
concentrate) and where his 'favorite' (high-price) vs underdog (low-price) buys sit + their profitability."""
import httpx,statistics,time
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
now=int(time.time()); T=[]
for x in A:
    s=x.get("slug","");parts=s.split("-")
    if "updown" not in s or len(parts)<4: continue
    coin=parts[0];dur=next((d for d in DUR if f"-{d}-" in s),None)
    if coin not in SYM or not dur: continue
    try: st=int(parts[-1])
    except: continue
    if st+DUR[dur]>now-30: continue
    T.append({"coin":coin,"dur":dur,"st":st,"side":x.get("outcome"),"price":x.get("price") or 0,"size":x.get("size") or 0})
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
        t["cost"]=t["size"]*t["price"]; t["profit"]=t["size"]*(1-t["price"]) if t["won"] else -t["size"]*t["price"]
    else: t["won"]=None
T=[t for t in T if t["won"] is not None]
TOT=sum(t["cost"] for t in T)
print("ce25 已结算BUY %d笔 | 总投入 $%.0f\n"%(len(T),TOT))
BANDS=[(0,0.15,"深longshot<0.15"),(0.15,0.3,"0.15-0.3"),(0.3,0.45,"0.3-0.45"),(0.45,0.55,"0.45-0.55"),
       (0.55,0.7,"0.55-0.7"),(0.7,0.85,"0.7-0.85favorite"),(0.85,1.01,">=0.85强favorite")]
print("%-18s %5s %8s %6s %6s %5s %8s %6s"%("价格档","笔","总投入$","%金额","均注$","胜%","盈亏$","ROI%"))
for lo,hi,l in BANDS:
    g=[t for t in T if lo<=t["price"]<hi]
    if not g: continue
    cost=sum(t["cost"] for t in g); pf=sum(t["profit"] for t in g)
    print("%-18s %5d %8.0f %5.0f%% %6.2f %4.0f%% %+8.1f %+5.1f"%(l,len(g),cost,cost/TOT*100,statistics.mean(t["size"]*t["price"] for t in g),sum(1 for t in g if t["won"])/len(g)*100,pf,pf/cost*100 if cost else 0))
print("\n=== 重注区 (按“平均单注$”看他在哪下重手) ===")
for lo,hi,l in BANDS:
    g=[t for t in T if lo<=t["price"]<hi]
    if g:
        big=sorted(g,key=lambda t:-t["cost"])[:3]
        print("  %-18s 均注$%.2f 中位$%.2f 最大3笔$%s"%(l,statistics.mean(t["cost"] for t in g),statistics.median(t["cost"] for t in g),",".join("%.0f"%t["cost"] for t in big)))
print("\n=== favorite(>=0.5) vs underdog(<0.5): 金额 + 盈亏 ===")
for nm,sel in (("favorite>=0.5",lambda p:p>=0.5),("underdog<0.5",lambda p:p<0.5)):
    g=[t for t in T if sel(t["price"])]
    cost=sum(t["cost"] for t in g); pf=sum(t["profit"] for t in g)
    print("  %-14s n=%-4d 投入$%.0f(%.0f%%) 胜%.0f%% 盈亏$%+.1f ROI%+.1f%% 均价%.2f"%(nm,len(g),cost,cost/TOT*100,sum(1 for t in g if t["won"])/len(g)*100,pf,pf/cost*100 if cost else 0,statistics.mean(t["price"] for t in g)))
