"""Reverse-engineer ce25's SELECTION function. Neutral band is breakeven but ce25 gets +25% in it -> what
does he key on WITHIN a price band? Build the 2D win surface: price-band x binance-lead-toward-his-side
(at buy time). If within each price band higher lead-toward-side => higher win, his selection signal =
the underlying lead direction (= our z-score) applied broadly. Also: does he SIZE by lead (value-weight)?"""
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
    T.append({"coin":coin,"dur":dur,"st":st,"side":x.get("outcome"),"price":x.get("price") or 0,"size":x.get("size") or 0,"ts":x.get("timestamp",st)})
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
    o=KL[t["coin"]].get(t["st"]);cl=KL[t["coin"]].get(t["st"]+DUR[t["dur"]])
    op=o[0] if o else None
    win=("Up" if cl[1]>=op else "Down") if (cl and op) else None
    bp=pxat(t["coin"],int(t["ts"]))
    t["lead"]=(math.log(bp/op)*1e4*(1 if t["side"]=="Up" else -1)) if (bp and op) else None
    t["won"]=(t["side"]==win) if win else None
T=[t for t in T if t["won"] is not None and t["lead"] is not None]
print("ce25 可分析BUY: %d\n"%len(T))
PB=[(0,0.25,"价<0.25"),(0.25,0.4,"0.25-0.4"),(0.4,0.6,"0.4-0.6"),(0.6,0.8,"0.6-0.8"),(0.8,1.01,">=0.8")]
LB=[(-99,-8,"领先<-8"),(-8,-2,"-8~-2"),(-2,2,"-2~2"),(2,8,"2~8"),(8,99,">=8")]
print("=== 二维胜率面: 价格档(行) × 标的领先档(列) ===  [每格: 胜%/笔数]")
print("            "+"".join("%-12s"%l[2] for l in LB))
for plo,phi,pl in PB:
    row="  %-10s"%pl
    for llo,lhi,ll in LB:
        rs=[t for t in T if plo<=t["price"]<phi and llo<=t["lead"]<lhi]
        row+= ("%2.0f%%/%-7d"%(sum(1 for t in rs if t["won"])/len(rs)*100,len(rs))) if rs else "  -/0      "
    print(row)
print("\n=== 他是否按领先 加大注码? (value-weight) ===")
for llo,lhi,ll in LB:
    rs=[t for t in T if llo<=t["lead"]<lhi]
    if rs: print("  %-10s n=%-4d 均注$%.2f 中位注$%.2f 胜%2.0f%%"%(ll,len(rs),statistics.mean(t["size"]*t["price"] for t in rs),statistics.median(t["size"]*t["price"] for t in rs),sum(1 for t in rs if t["won"])/len(rs)*100))
print("\n=== 结论判据: 固定价格档内, 胜率随领先单调上升? ===")
for plo,phi,pl in PB:
    sub=[(t["lead"],t["won"]) for t in T if plo<=t["price"]<phi]
    if len(sub)<30: continue
    neg=[w for l,w in sub if l<0]; pos=[w for l,w in sub if l>=0]
    if neg and pos:
        print("  %-10s 领先<0胜%2.0f%%(n%d) vs 领先>=0胜%2.0f%%(n%d)  差%+.0fpp"%(pl,sum(neg)/len(neg)*100,len(neg),sum(pos)/len(pos)*100,len(pos),(sum(pos)/len(pos)-sum(neg)/len(neg))*100))
