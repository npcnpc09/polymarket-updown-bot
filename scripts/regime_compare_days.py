"""regime_compare_days.py — what's different about btc on 06-11/12 (big green, 93% win) vs 06-16->now (choppy
/red)? Fetch btc 1m klines for each period, compute: realized vol, flip-rate, efficiency-ratio (trend vs chop),
and THE key driver — the 5m-window REVERSAL RATE (early-lead sign @ min3 vs settle sign). High reversal rate =
our directional bets get whipsawed = win% drops below the ~84% breakeven."""
import httpx, math, statistics as st
SYM="BTCUSDT"
def klines(t0,t1):
    out=[]; t=t0
    with httpx.Client(timeout=25) as c:
        while t<t1:
            k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM,"interval":"1m","startTime":t*1000,"endTime":t1*1000,"limit":1000}).json()
            if not isinstance(k,list) or not k: break
            for r in k: out.append((r[0]//1000,float(r[1]),float(r[4])))  # ts,open,close
            t=k[-1][0]//1000+60
            if len(k)<1000: break
    return out
def analyze(t0,t1,label):
    k=klines(t0,t1)
    closes=[x[2] for x in k]; rets=[math.log(closes[i]/closes[i-1])*1e4 for i in range(1,len(closes))]
    vol=st.pstdev(rets); sg=[1 if r>=0 else -1 for r in rets]
    flip=sum(1 for i in range(1,len(sg)) if sg[i]!=sg[i-1])/(len(sg)-1)
    er=abs(sum(rets))/sum(abs(r) for r in rets) if rets else 0
    # 5m-window reversal: lead@min3 sign vs settle sign (open->close of the 5m window)
    O={t:o for t,o,c in k}; C={t:c for t,o,c in k}
    rev=0; nwin=0; per5=0
    t=t0-(t0%300)
    while t+300<=t1:
        op=O.get(t); m3=C.get(t+180); cl=C.get(t+300) or O.get(t+300)
        if op and m3 and cl:
            lead3=m3-op
            if abs(math.log(m3/op)*1e4)>=8:  # only windows with a real early lead (the ones we'd trade)
                nwin+=1; per5+=1
                if (lead3>=0)!=(cl>=op): rev+=1
        t+=300
    print(f"=== {label} ===")
    print(f"   1m realized-vol={vol:.1f}bps  flip-rate={flip:.2f}  efficiency-ratio(ER)={er:.3f}  ({len(k)} 1m-bars)")
    print(f"   5m windows with |early-lead|>=8: {nwin}  ->  REVERSAL rate(early-dir != settle) = {rev/nwin*100 if nwin else 0:.1f}%")
# periods
GREEN=(1781136000,1781308800)      # 06-11 00:00 -> 06-13 00:00 UTC (the +$50/+$37 days)
RECENT=(1781568000,1781856000)     # 06-16 00:00 -> 06-19 ~12:00 UTC (the choppy/red stretch)
analyze(*GREEN,"GREEN days 06-11/06-12 (93% win, +$88)")
analyze(*RECENT,"RECENT days 06-16->06-19 (mixed/red)")
print("\nREAD: green-day market should show LOWER reversal rate + HIGHER ER (trending, moves persist) -> our")
print("directional bets win. Recent should show HIGHER reversal + LOWER ER (choppy) -> win% dips below breakeven.")
