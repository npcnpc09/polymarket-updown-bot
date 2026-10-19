"""Decode ce25's CHEAP-UNDERDOG selection (his profit engine). For his BUYs at price<0.5, reconstruct the
binance lead toward the bought side at his buy time. Hypothesis: his WINNING underdogs are the cheap side
the underlying is ALREADY moving toward (early value = the side about to become favorite, bought while still
cheap), and his LOSERS are underdogs AGAINST the lead (dead longshots). If true, the +EV cell = cheap +
lead-aligned, and THAT is a signal we (small) could select on."""
import httpx,math,statistics,time
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
    p=x.get("price") or 0
    if p>=0.5: continue  # UNDERDOG only
    T.append({"coin":coin,"dur":dur,"st":st,"side":x.get("outcome"),"price":p,"size":x.get("size") or 0,"ts":x.get("timestamp",st)})
need=set(t["coin"] for t in T);KL={}
for coin in need:
    out={};cur=min(t["st"] for t in T if t["coin"]==coin)-180;hi=max(t["st"]+DUR[t["dur"]] for t in T if t["coin"]==coin)+300
    while cur<hi:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[4]))
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    KL[coin]=out
def pxat(coin,t):
    d=KL[coin];lo=(t//60)*60;aa=d.get(lo);bb=d.get(lo+60)
    if not aa:return None
    return aa[0]+((bb[0]-aa[0])*((t-lo)/60.0) if bb else 0)
for t in T:
    o=KL[t["coin"]].get(t["st"]);cl=KL[t["coin"]].get(t["st"]+DUR[t["dur"]]);op=o[0] if o else None
    win=("Up" if cl[1]>=op else "Down") if (cl and op) else None
    bp=pxat(t["coin"],int(t["ts"]))
    t["lead"]=(math.log(bp/op)*1e4*(1 if t["side"]=="Up" else -1)) if (bp and op) else None   # toward his side
    t["won"]=(t["side"]==win) if win else None
    t["off"]=t["ts"]-t["st"]
    t["profit"]=(t["size"]*(1-t["price"]) if t["won"] else -t["size"]*t["price"]) if t["won"] is not None else None
T=[t for t in T if t["won"] is not None and t["lead"] is not None]
def stat(rs,lbl):
    if not rs: print("  %-22s n=0"%lbl);return
    cost=sum(t["size"]*t["price"] for t in rs); pf=sum(t["profit"] for t in rs)
    print("  %-22s n=%-4d 胜%2.0f%% ROI%+6.1f%% 盈亏$%+7.1f 均价%.2f"%(lbl,len(rs),sum(1 for t in rs if t["won"])/len(rs)*100,pf/cost*100 if cost else 0,pf,statistics.mean(t["price"] for t in rs)))
print("ce25 underdog(<0.5) 可分析 %d笔\n"%len(T))
print("=== 按 买入时 binance领先(朝他买的便宜侧) ===")
stat([t for t in T if t["lead"]<-8],"标的强反向<-8 (死longshot)")
stat([t for t in T if -8<=t["lead"]<-2],"弱反向 -8~-2")
stat([t for t in T if -2<=t["lead"]<2],"中性 -2~2")
stat([t for t in T if 2<=t["lead"]<8],"弱同向 2~8")
stat([t for t in T if t["lead"]>=8],"标的强同向>=8 (便宜赢家!)")
print("\n=== 关键: 便宜underdog里, lead朝它(>0) vs 反它(<0) ===")
stat([t for t in T if t["lead"]>=0],"lead朝它(>=0)")
stat([t for t in T if t["lead"]<0],"lead反它(<0)")
print("\n=== lead朝它 × 价格档 (能不能便宜买到将成favorite的赢家) ===")
al=[t for t in T if t["lead"]>=2]
for lo,hi,l in ((0,0.2,"<0.2"),(0.2,0.35,"0.2-0.35"),(0.35,0.5,"0.35-0.5")):
    stat([t for t in al if lo<=t["price"]<hi],"lead朝它 "+l)
print("\n=== 按买入时点 (早撒 vs 晚买已转向的) ===")
for lo,hi,l in ((0,60,"<60s"),(60,150,"60-150s"),(150,9999,">150s")):
    stat([t for t in T if lo<=t["off"]<hi],l)
