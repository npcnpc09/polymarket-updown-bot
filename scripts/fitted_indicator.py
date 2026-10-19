"""fitted_indicator.py — STOP using textbook market stats (vol/flip/ER). Build indicators FITTED to OUR exact
strategy mechanics (enter ~min3 on z>=2.5 & |lead|>=8, HOLD to settle), measured ONLY on windows WE'd trade,
over OUR holding window. Compare streak (06-09->13) vs recent (06-15->19). The breaker worked because it was
self-fitted (our outcomes); these are fitted to our ENTRY+HOLD mechanics."""
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
def analyze(t0,t1,label):
    print(f"=== {label} ===")
    for coin,sym in COINS.items():
        k=klines_1m(sym,t0,t1); O={t:o for t,o,c in k}; C={t:c for t,o,c in k}
        retain=[]; flips=[]; rev=0; nset=0; held_win=0
        t=t0-(t0%300)
        while t+300<=t1:
            op=O.get(t); m3=C.get(t+180); cl=C.get(t+300) or O.get(t+300)
            cl1=[C.get(t-60*i) for i in range(1,31)]; cl1=[x for x in cl1 if x]
            if op and m3 and cl and len(cl1)>=20:
                v30=st.pstdev([math.log(cl1[i]/cl1[i-1])*1e4 for i in range(1,len(cl1))])
                lead3=math.log(m3/op)*1e4
                if v30>0 and abs(lead3)>=8 and abs(lead3)/v30>=2.5:   # OUR setup
                    nset+=1
                    lead5=math.log(cl/op)*1e4
                    # 1) lead retention: |lead@settle| / |lead@entry|, signed toward entry dir
                    signed_ret=(lead5 if lead3>=0 else -lead5)/abs(lead3)
                    retain.append(signed_ret)
                    # 2) final-stretch (min3->min5) 1m-return sign flips — OUR hold window only
                    pts=[C.get(t+180),C.get(t+240),C.get(t+300) or O.get(t+300)]
                    if all(p is not None for p in pts):
                        r=[pts[1]-pts[0],pts[2]-pts[1]]; sg=[1 if x>=0 else -1 for x in r]
                        flips.append(1 if sg[0]!=sg[1] else 0)
                    # 3) reversal + win
                    won=((lead3>=0)==(cl>=op))
                    if not won: rev+=1
                    else: held_win+=1
            t+=300
        if nset:
            print(f"  {coin}: setups={nset:3d} | lead-RETENTION(settle/entry)={st.mean(retain):+.2f} (1.0=held, <0=reversed)"
                  f" | hold-flip-rate={st.mean(flips)*100 if flips else 0:.0f}% | reversal={rev/nset*100:.1f}% win={held_win/nset*100:.1f}%")
STREAK=(1780963200,1781308800); RECENT=(1781481600,1781871880)
analyze(*STREAK,"STREAK 06-09->06-13 (91+84 cell wins)")
analyze(*RECENT,"RECENT 06-15->06-19 (choppy/red)")
print("\nREAD (fitted to us): lead-RETENTION = does our late favorite HOLD its lead to settle (good, ~>=1) or")
print("FADE/reverse (bad, <1 or negative)? hold-flip-rate = whipsaw DURING our hold. If streak has higher")
print("retention / lower hold-flips than recent -> THAT is the strategy-fitted separating indicator.")
