"""Is eebde's FAVORITE a TREND selection (binance-lead-aligned side) entered EARLY? For his favorite buys
(>=0.5): reconstruct binance lead toward the bought side at buy time (DIRECTION is reliable; OUTCOME uses
real redeems, not binance). Split by lead-aligned vs against, and by entry timing. If his +EV favorites are
the lead-aligned ones bought early/cheap -> that IS 'z-gated early maker', and his real +ROI validates it."""
import httpx,math,statistics,time
from collections import defaultdict
EE="0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
A=[]
for off in range(0,4000,500):
    try: a=c.get("https://data-api.polymarket.com/activity",params={"user":EE,"limit":500,"offset":off}).json()
    except: break
    if not isinstance(a,list) or not a: break
    A+=a
    if len(a)<500: break
SYM={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT","xrp":"XRPUSDT","doge":"DOGEUSDT"}; DUR={"5m":300,"15m":900}; OUT=["Up","Down"]
W={}
for r in A:
    s=r.get("slug","")
    if "updown" not in s: continue
    parts=s.split("-"); coin=parts[0]; dur=next((d for d in DUR if f"-{d}-" in s),None)
    if coin not in SYM or not dur: continue
    try: st=int(parts[-1])
    except: continue
    w=W.setdefault(s,{"coin":coin,"dur":dur,"st":st,"buys":[],"ridx":None,"rsize":0.0})
    t=r.get("type")
    if t=="TRADE" and r.get("side","").upper()=="BUY":
        w["buys"].append({"oc":r.get("outcome"),"price":r.get("price") or 0,"size":r.get("size") or 0,"ts":r.get("timestamp",st)})
    elif t=="REDEEM":
        w["rsize"]+=r.get("size") or 0
        if r.get("outcomeIndex") is not None: w["ridx"]=r.get("outcomeIndex")
def winner(w):
    if w["ridx"] in (0,1): return OUT[w["ridx"]]
    if w["rsize"]>0:
        up=sum(b["size"] for b in w["buys"] if b["oc"]=="Up"); dn=sum(b["size"] for b in w["buys"] if b["oc"]=="Down")
        return "Up" if abs(w["rsize"]-up)<abs(w["rsize"]-dn) else "Down"
    return None
res={s:w for s,w in W.items() if winner(w)}
need=set(w["coin"] for w in res.values()); KL={}
for coin in need:
    sts=[w["st"] for w in res.values() if w["coin"]==coin]
    out={};cur=min(sts)-180;hi=max(w["st"]+DUR[w["dur"]] for w in res.values() if w["coin"]==coin)+300
    while cur<hi:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[4]))
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    KL[coin]=out
def pxat(coin,t):
    d=KL.get(coin,{});lo=(t//60)*60;aa=d.get(lo);bb=d.get(lo+60)
    if not aa:return None
    return aa[0]+((bb[0]-aa[0])*((t-lo)/60.0) if bb else 0)
fav=[]  # favorite buys with lead+timing+real outcome
for s,w in res.items():
    win=winner(w); op=KL.get(w["coin"],{}).get(w["st"])
    op=op[0] if op else None
    if not op: continue
    for b in w["buys"]:
        if b["price"]<0.5: continue
        bp=pxat(w["coin"],int(b["ts"]))
        lead=(math.log(bp/op)*1e4*(1 if b["oc"]=="Up" else -1)) if bp else None  # toward his side
        fav.append({"price":b["price"],"size":b["size"],"won":b["oc"]==win,"lead":lead,"off":b["ts"]-w["st"]})
fav=[f for f in fav if f["lead"] is not None]
print("eebde favorite买入(可分析) %d笔\n"%len(fav))
def stat(rs,lbl):
    if not rs: print("  %-22s n=0"%lbl);return
    cost=sum(f["price"]*f["size"] for f in rs); pf=sum(f["size"]*(1-f["price"]) if f["won"] else -f["size"]*f["price"] for f in rs)
    print("  %-22s n=%-4d 真胜%2.0f%% 均价%.3f 均lead%+5.1f ROI%+6.1f%%"%(lbl,len(rs),sum(1 for f in rs if f["won"])/len(rs)*100,statistics.mean(f["price"] for f in rs),statistics.mean(f["lead"] for f in rs),pf/cost*100 if cost else 0))
print("=== favorite 是不是趋势选择? 按 买入时binance领先(朝他买的favorite侧) ===")
stat([f for f in fav if f["lead"]<-5],"标的反向<-5 (逆势favorite)")
stat([f for f in fav if -5<=f["lead"]<5],"中性 -5~5")
stat([f for f in fav if 5<=f["lead"]<15],"顺势 5~15")
stat([f for f in fav if f["lead"]>=15],"强顺势>=15")
print("\n=== favorite 早入还是晚入? 按时点 ===")
for lo,hi,l in ((0,60,"<60s早"),(60,150,"60-150s"),(150,9999,">150s晚")):
    stat([f for f in fav if lo<=f["off"]<hi],l)
print("\n=== 交叉: 顺势(lead>=5)favorite × 早晚 ===")
al=[f for f in fav if f["lead"]>=5]
stat([f for f in al if f["off"]<90],"顺势favorite 早入<90s")
stat([f for f in al if f["off"]>=90],"顺势favorite 晚入>=90s")
print("\n均入场时点: %.0fs | 顺势(lead>=5)占favorite: %.0f%%"%(statistics.mean(f["off"] for f in fav),sum(1 for f in fav if f["lead"]>=5)/len(fav)*100))
