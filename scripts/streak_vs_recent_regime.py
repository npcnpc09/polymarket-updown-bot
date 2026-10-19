"""streak_vs_recent_regime.py — hunt for ONE indicator separating the 91-win-streak period (06-09->06-13) from
the recent choppy stretch (06-15->06-19). Rich suite incl. ones not tried before: return AUTOCORRELATION (trend
persistence) and the CELL-SPECIFIC late-z reversal rate (early-dir vs settle on z>=2.5 setups = the closest
proxy to the cell loss rate). btc+eth, binance 1m/1s."""
import httpx, math, statistics as st
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}
def klines_1m(sym,t0,t1):
    out=[]; t=t0
    with httpx.Client(timeout=25) as c:
        while t<t1:
            k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":t*1000,"endTime":t1*1000,"limit":1000}).json()
            if not isinstance(k,list) or not k: break
            for r in k: out.append((r[0]//1000,float(r[1]),float(r[4])))
            t=k[-1][0]//1000+60
            if len(k)<1000: break
    return out
def autocorr(x,lag=1):
    if len(x)<lag+2: return 0
    m=st.mean(x); v=sum((a-m)**2 for a in x)
    if v==0: return 0
    return sum((x[i]-m)*(x[i-lag]-m) for i in range(lag,len(x)))/v
def analyze(t0,t1,label):
    agg={}
    for coin,sym in COINS.items():
        k=klines_1m(sym,t0,t1); O={t:o for t,o,c in k}; C={t:c for t,o,c in k}
        closes=[x[2] for x in k]; rets=[math.log(closes[i]/closes[i-1])*1e4 for i in range(1,len(closes))]
        vol=st.pstdev(rets); sg=[1 if r>=0 else -1 for r in rets]
        flip=sum(1 for i in range(1,len(sg)) if sg[i]!=sg[i-1])/(len(sg)-1)
        ac1=autocorr(rets,1)
        # 5m-window reversal on late-z setups (z>=2.5 & |lead|>=8 at min3) — cell proxy
        rev=0; nset=0
        t=t0-(t0%300)
        while t+300<=t1:
            op=O.get(t); m3=C.get(t+180); cl=C.get(t+300) or O.get(t+300)
            cl1=[C.get(t-60*i) for i in range(1,31)]; cl1=[x for x in cl1 if x]
            if op and m3 and cl and len(cl1)>=20:
                v30=st.pstdev([math.log(cl1[i]/cl1[i-1])*1e4 for i in range(1,len(cl1))])
                lead=math.log(m3/op)*1e4
                if v30>0 and abs(lead)>=8 and abs(lead)/v30>=2.5:
                    nset+=1
                    if (lead>=0)!=(cl>=op): rev+=1
            t+=300
        agg[coin]={"vol":vol,"flip":flip,"ac1":ac1,"nset":nset,"rev":rev/nset*100 if nset else 0}
    print(f"=== {label} ===")
    for coin in COINS:
        a=agg[coin]
        print(f"  {coin}: vol={a['vol']:.1f}  flip={a['flip']:.2f}  ret-autocorr(lag1)={a['ac1']:+.3f}  late-z setups={a['nset']:3d} REVERSAL={a['rev']:.1f}%")
STREAK=(1780963200,1781308800)   # 06-09 -> 06-13
RECENT=(1781481600,1781871880)   # 06-15 -> 06-19 now
analyze(*STREAK,"STREAK period 06-09->06-13 (91+84 cell wins)")
analyze(*RECENT,"RECENT period 06-15->06-19 (choppy/red)")
print("\nREAD: ret-autocorr(lag1) POSITIVE = trending (moves persist -> cell wins); NEGATIVE = mean-reverting")
print("(whipsaw -> cell loses). If streak has higher autocorr / lower late-z reversal than recent -> THAT is")
print("the separating indicator. If all ~equal -> confirms no price-regime difference (incidence/luck).")
