"""How does ce25 pick winners? For each BUY, reconstruct the binance lead TOWARD his bought side AT his
buy time, the buy timing (offset in window), and the price. Split profit/win by each to see what he keys
on: does he buy the side that's LEADING in the underlying but still cheap (PM-lags-underlying value), or
contrarian laggards? early or late? which price band actually profits?"""
import httpx,json,math,statistics,time,datetime
from collections import defaultdict
CE="0xcE25E214D5cfE4f459cf67F08DF581885AAE7Fdc"
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
A=[]
for off in range(0,3000,500):
    try: a=c.get("https://data-api.polymarket.com/activity",params={"user":CE,"limit":500,"offset":off}).json()
    except: break
    if not isinstance(a,list) or not a: break
    A+=[x for x in a if x.get("type")=="TRADE" and (x.get("side") or "").upper()=="BUY"]
    if len(a)<500: break
SYM={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT","xrp":"XRPUSDT","doge":"DOGEUSDT"}; DUR={"5m":300,"15m":900}
now=int(time.time())
T=[]
for x in A:
    s=x.get("slug",""); parts=s.split("-")
    if "updown" not in s or len(parts)<4: continue
    coin=parts[0]; dur=next((d for d in DUR if f"-{d}-" in s),None)
    if coin not in SYM or not dur: continue
    try: st=int(parts[-1])
    except: continue
    if st+DUR[dur]>now-30: continue
    T.append({"coin":coin,"dur":dur,"st":st,"side":x.get("outcome"),"price":x.get("price") or 0,"size":x.get("size") or 0,"ts":x.get("timestamp",st)})
print("已结算BUY: %d\n"%len(T))
need=set(t["coin"] for t in T); KL={}
for coin in need:
    out={};cur=min(t["st"] for t in T if t["coin"]==coin)-120;hi=max(t["st"]+DUR[t["dur"]] for t in T if t["coin"]==coin)+300
    while cur<hi:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[4]))
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    KL[coin]=out
def pxat(coin,t):
    d=KL[coin];lo=(t//60)*60;hi=lo+60;a=d.get(lo);b=d.get(hi)
    if not a:return None
    a=a[1] if lo in d else None  # use close of that minute... use open of bucket
    aa=d.get(lo);bb=d.get(hi)
    if not aa:return None
    av=aa[0]  # open
    if not bb:return av
    return av+(bb[0]-av)*((t-lo)/60.0)
for t in T:
    o=KL[t["coin"]].get(t["st"]); cl=KL[t["coin"]].get(t["st"]+DUR[t["dur"]])
    op=o[0] if o else None
    t["win"]=("Up" if (cl and op and cl[1]>=op) else ("Down" if cl else None)) if op else None
    bp=pxat(t["coin"],int(t["ts"]))
    t["lead"]=(math.log(bp/op)*1e4*(1 if t["side"]=="Up" else -1)) if (bp and op) else None
    t["off"]=t["ts"]-t["st"]
    t["won"]=(t["side"]==t["win"]) if t["win"] else None
    t["profit"]=(t["size"]*(1-t["price"]) if t["won"] else -t["size"]*t["price"]) if t["won"] is not None else None
T=[t for t in T if t["profit"] is not None and t["lead"] is not None]
def grp(rs,lbl):
    if not rs: print("  %-22s n=0"%lbl);return
    sp=sum(t["size"]*t["price"] for t in rs)
    print("  %-22s n=%-4d 胜%2.0f%% 盈亏$%+7.1f ROI%+5.1f%% 均价%.2f"%(lbl,len(rs),sum(1 for t in rs if t["won"])/len(rs)*100,sum(t["profit"] for t in rs),sum(t["profit"] for t in rs)/sp*100 if sp else 0,statistics.mean(t["price"] for t in rs)))
print("=== 按 买入时标的领先(朝他买的侧) ===")
grp([t for t in T if t["lead"]<-8],"标的强反向(<-8)")
grp([t for t in T if -8<=t["lead"]<0],"标的弱反向(-8~0)")
grp([t for t in T if 0<=t["lead"]<8],"标的弱同向(0~8)")
grp([t for t in T if t["lead"]>=8],"标的强同向(>=8)")
print("\n=== 按 买入价 ===")
for lo,hi,l in ((0,0.25,"<0.25"),(0.25,0.4,"0.25-0.4"),(0.4,0.5,"0.4-0.5"),(0.5,0.7,"0.5-0.7"),(0.7,1,">=0.7")):
    grp([t for t in T if lo<=t["price"]<hi],l)
print("\n=== 按 买入时点(窗口内秒) ===")
for lo,hi,l in ((0,60,"<60s早"),(60,150,"60-150s"),(150,300,"150-300s"),(300,9999,">300s(15m)")):
    grp([t for t in T if lo<=t["off"]<hi],l)
