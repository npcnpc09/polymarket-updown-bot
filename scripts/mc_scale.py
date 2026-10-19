"""Minimum scale for value-weight + diversification. Monte-Carlo by RESAMPLING ce25's real trades
(joint size/price/win), build equity curves, measure: (a) max cumulative loss from start = the bankroll
you must exceed to avoid ruin, (b) max drawdown. Compare VALUE-WEIGHT (his real sizes) vs FLAT (same
trades, avg size) to isolate how much MORE bankroll value-weighting needs. Sweep N (windows) to show how
diversification shrinks RELATIVE risk. Report in units of avg-bet so it scales to any bet size we pick."""
import httpx,math,statistics,random
random.seed(0)  # Math.random unavailable note n/a (python); fixed seed for reproducibility
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
import time; now=int(time.time())
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
vw=[]; flat=[]; sizes=[]
for t in T:
    o=KL[t["coin"]].get(t["st"]);cl=KL[t["coin"]].get(t["st"]+DUR[t["dur"]])
    if not o or not cl: continue
    won=(t["side"]==("Up" if cl[1]>=o[0] else "Down")); p=t["price"]; sz=t["size"]
    if sz<=0 or p<=0: continue
    vw.append((sz,p,won)); sizes.append(sz)
avg=statistics.mean(sizes)
prof_vw=[sz*(1-p) if w else -sz*p for sz,p,w in vw]
prof_flat=[avg*(1-p) if w else -avg*p for sz,p,w in vw]
ev_vw=sum(prof_vw); ev_flat=sum(prof_flat)
print("ce25 真实成交 n=%d | 均注$%.2f | 加注EV/笔$%+.3f 平注EV/笔$%+.3f\n"%(len(vw),avg,ev_vw/len(vw),ev_flat/len(vw)))
def mc(profits,N,K=4000):
    """K paths of N resampled trades. Return (p50,p95,p99 of max-cum-loss-from-start), p50 maxDD, P(final<0)."""
    worst=[]; dd=[]; neg=0
    pool=profits; n=len(pool)
    for _ in range(K):
        eq=0.0; peak=0.0; mn=0.0; mdd=0.0
        for _ in range(N):
            eq+=pool[random.randrange(n)]
            if eq<mn: mn=eq
            if eq>peak: peak=eq
            if peak-eq>mdd: mdd=peak-eq
        worst.append(-mn); dd.append(mdd); neg+= 1 if eq<0 else 0
    worst.sort(); dd.sort()
    return worst[K//2],worst[int(K*.95)],worst[int(K*.99)],dd[K//2],neg/K
print("=== 必备本金 = 起点最大累计亏损(才不破产), 单位:$ (按ce25均注$%.2f) ==="%avg)
print("  N(窗口)   加注:中位/p95/p99破产线   平注:p99破产线   加注终亏概率")
for N in (20,50,144,500,1000,2500):
    w50,w95,w99,d50,pneg=mc(prof_vw,N)
    f50,f95,f99,fd50,fpneg=mc(prof_flat,N)
    print("  %-7d  $%5.0f/$%5.0f/$%5.0f          $%5.0f            %4.1f%%   (平注终亏%4.1f%%)"%(N,w50,w95,w99,f99,pneg*100,fpneg*100))
print("\n=== 换算: 不同均注下, 安全跑value-weight所需最小本金 (p99破产线×1.5安全垫, N=500≈我们btc/eth几天) ===")
w50,w95,w99,d50,pneg=mc(prof_vw,500)
for betmult,lbl in ((avg,"照ce25均注$%.1f"%avg),(4.0,"我们当前5股~$4"),(2.0,"小注$2"),(9.0,"$9/注")):
    scale=betmult/avg
    print("  %-18s p99破产线$%.0f → 建议本金 ≥ $%.0f (含1.5x安全垫)"%(lbl,w99*scale,w99*scale*1.5))
print("\n注: 重采样把交易当独立 -> 低估了 btc+eth 同窗相关亏损(我们z-maker真出过). 实际再留 ~20-30% 余量.")
