"""Week-scale capital simulation of ce25's pattern. We LACK a week of real PM prices, so we bootstrap ce25's
REAL trade return-distribution (his actual size/price/outcome) over a week's worth of trades at several
capital sizes. Reports week return, max drawdown, ruin. HEAVY CAVEAT: outcomes are binance-reconstructed
(inflates cheap longshots — see binance-reconstruction-inflates-longshots), and it ASSUMES we replicate his
selection -> this is an OPTIMISTIC UPPER BOUND, real would be lower. Only an on-chain real probe is truth."""
import httpx,math,statistics,random
random.seed(0)
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
import time; now=int(time.time()); T=[]
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
rets=[]  # per-$ return of one resampled ce25 trade
for t in T:
    o=KL[t["coin"]].get(t["st"]);cl=KL[t["coin"]].get(t["st"]+DUR[t["dur"]])
    if not o or not cl or t["price"]<=0: continue
    won=(t["side"]==("Up" if cl[1]>=o[0] else "Down"))
    rets.append((1-t["price"])/t["price"] if won else -1.0)
n=len(rets); mu=statistics.mean(rets)
print("ce25 真实成交 %d笔 | 每$投入回报 均值%+.3f (=%.1f%%/笔, binance重建-上限)\n"%(n,mu,mu*100))
PER_DAY=179; WEEK=PER_DAY*7  # his pace ~179 settled/day
print("一周交易数 ~%d (按他~%d/天)\n"%(WEEK,PER_DAY))
def sim(cap,frac,K=4000):
    """K paths: WEEK trades, each stake=frac*cap (flat, diversified), bootstrap ce25 returns."""
    fin=[];dd=[];ruin=0
    for _ in range(K):
        eq=cap;peak=cap;mdd=0
        for _ in range(WEEK):
            eq+=frac*cap*rets[random.randrange(n)]
            if eq>peak:peak=eq
            if peak-eq>mdd:mdd=peak-eq
            if eq<=0:ruin+=1;break
        fin.append(eq/cap-1);dd.append(mdd/cap)
    fin.sort()
    return statistics.median(fin)*100,fin[int(K*.1)]*100,statistics.median(dd)*100,ruin/K*100
print("=== 一周模拟 (每窗下 本金的frac, 分散, %d笔) ==="%WEEK)
print("  %-26s 中位周收益 p10(差运气) 中位回撤 破产%%"%"资金/每注")
for cap in (500,1000,5000):
    for frac in (0.005,0.01,0.02):
        m,p,d,r=sim(cap,frac)
        print("  $%-5d 每注%.1f%%($%4.0f)   %+7.1f%%  %+7.1f%%  %6.1f%%  %4.1f%%"%(cap,frac*100,cap*frac,m,p,d,r))
print("\n注: 这是上限 (binance重建灌水 + 假设我们能复制他的选择). 真实会更低, 可能薄很多.")
print("真正能信的只有: 真钱在Chainlink结算下跑一周. 这个模拟只回答'若edge是真的, 规模够不够扛方差'.")
