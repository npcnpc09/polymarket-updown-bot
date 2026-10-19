"""bt_preentry_chop.py — FITTED, entry-time, fine-grained indicator: when our setup reaches |lead|>=8 & z>=2.5
at ~min3, did it get there via a CLEAN trend or a CHOPPY path? Measure pre-entry path-flips (sign changes of
10s-bucketed returns over min0->min3, the path we CAN see at entry). Test: does a choppy path predict the
window REVERSING by settle? If high pre-entry-flips -> lower win% -> an actionable SKIP filter (don't enter on
a choppy bounce). This is the 'clean breakout vs choppy bounce' question, fitted to our entry."""
import httpx, math, statistics as st
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}; HOURS=96
import time
now=int(time.time()); start=now-HOURS*3600
def fetch_1s(sym,t0,t1):
    out=[]; t=t0
    with httpx.Client(timeout=25) as c:
        while t<t1:
            k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1s","startTime":t*1000,"limit":1000}).json()
            if not isinstance(k,list) or not k: break
            for r in k: out.append((r[0]//1000,float(r[4])))
            t=k[-1][0]//1000+1
            if len(k)<1000: break
    return out
rows=[]
for coin,sym in COINS.items():
    bars=fetch_1s(sym,start,now); P={t:px for t,px in bars}; c1m={t:px for t,px in bars if t%60==0}
    W={}
    for t,px in bars: W.setdefault((t//300)*300,{})[t-(t//300)*300]=px
    for ws,pts in W.items():
        if 0 not in pts: continue
        opn=pts[0]; m3=pts.get(180) or pts.get(179) or pts.get(181)
        settle=W.get(ws+300,{}).get(0) or pts.get(299)
        if m3 is None or settle is None: continue
        cl1=[c1m.get(ws-60*i) for i in range(1,31)]; cl1=[x for x in cl1 if x]
        if len(cl1)<20: continue
        v30=st.pstdev([math.log(cl1[i]/cl1[i-1])*1e4 for i in range(1,len(cl1))])
        lead3=math.log(m3/opn)*1e4
        if not(v30>0 and abs(lead3)>=8 and abs(lead3)/v30>=2.5): continue   # OUR setup
        # pre-entry path flips: 10s-bucketed closes min0..min180, sign-changes of returns
        seq=[pts.get(s) for s in range(0,181,10)]; seq=[x for x in seq if x is not None]
        if len(seq)<12: continue
        r=[seq[i]-seq[i-1] for i in range(1,len(seq))]; sg=[1 if x>=0 else -1 for x in r]
        flips=sum(1 for i in range(1,len(sg)) if sg[i]!=sg[i-1])
        won=((lead3>=0)==(settle>=opn))
        rows.append({"flips":flips,"won":won,"lead":abs(lead3)})
def rep(s,lab):
    if not s: print(f"  {lab:22s} n=0"); return
    w=sum(1 for r in s if r["won"])
    print(f"  {lab:22s} n={len(s):4d} win%={w/len(s)*100:5.1f}  avgFlips={st.mean([r['flips'] for r in s]):.1f}")
print(f"OUR setups ({HOURS}h btc+eth): {len(rows)}  base win% {sum(1 for r in rows if r['won'])/len(rows)*100:.1f}")
print("flips = sign-changes of 10s-returns in min0->min3 (max ~17). LOW=clean trend, HIGH=choppy path\n")
fl=sorted(r["flips"] for r in rows)
print(f"flip distribution: min={fl[0]} median={fl[len(fl)//2]} max={fl[-1]}")
rep([r for r in rows if r["flips"]<=6],"clean (flips<=6)")
rep([r for r in rows if 7<=r["flips"]<=9],"medium (7-9)")
rep([r for r in rows if r["flips"]>=10],"choppy (flips>=10)")
print("\n  candidate gate: SKIP choppy-path setups")
rep(rows,"ALL (no gate)")
rep([r for r in rows if r["flips"]<=8],"KEEP flips<=8")
rep([r for r in rows if r["flips"]>8],"  (dropped flips>8)")
print("\nREAD: if win% DROPS monotonically with pre-entry flips and the choppy bucket is clearly lower -> a")
print("clean-path entry filter is real & actionable (skip choppy bounces). If flat -> path-choppiness carries")
print("no info beyond the lead itself (another refuted price feature).")
