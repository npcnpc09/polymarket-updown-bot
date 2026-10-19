"""bt_preentry_chop_big.py — bigger-sample + held-out test of the pre-entry path-choppiness signal. Reconstruct
~7d of OUR setups (z>=2.5 & |lead|>=8 @min3), compute min0->min3 10s-bucketed sign-flips, win = binance settle.
Tests: (1) win% by flip bucket, (2) TRAIN/HELD-OUT split (does clean>choppy hold OOS?), (3) the binary very-clean
(<=6) vs rest split the real-fill sample pointed to. CAVEAT: reconstruction win% inflated vs real; read the
SHAPE/robustness, not absolutes. Real-fill validation still needs live instrumentation."""
import httpx, math, statistics as st, time
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}; HOURS=168
now=int(time.time()); start=now-HOURS*3600
def fetch_1s(sym,t0,t1):
    out=[]; t=t0
    with httpx.Client(timeout=25) as c:
        while t<t1:
            try: k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1s","startTime":t*1000,"limit":1000}).json()
            except: time.sleep(1); continue
            if not isinstance(k,list) or not k: break
            for r in k: out.append((r[0]//1000,float(r[4])))
            t=k[-1][0]//1000+1
            if len(k)<1000: break
    return out
rows=[]
for coin,sym in COINS.items():
    bars=fetch_1s(sym,start,now)
    if not bars: print(f"{coin}: no 1s data"); continue
    c1m={t:px for t,px in bars if t%60==0}; W={}
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
        if not(v30>0 and abs(lead3)>=8 and abs(lead3)/v30>=2.5): continue
        seq=[pts.get(s) for s in range(0,181,10)]; seq=[x for x in seq if x is not None]
        if len(seq)<12: continue
        r=[seq[i]-seq[i-1] for i in range(1,len(seq))]; sg=[1 if x>=0 else -1 for x in r]
        flips=sum(1 for i in range(1,len(sg)) if sg[i]!=sg[i-1])
        rows.append({"ws":ws,"flips":flips,"won":((lead3>=0)==(settle>=opn))})
rows.sort(key=lambda x:x["ws"])
def rep(s,lab):
    if not s: print(f"  {lab:20s} n=0"); return
    w=sum(1 for x in s if x["won"]); print(f"  {lab:20s} n={len(s):4d} win%={w/len(s)*100:5.1f} avgFlips={st.mean([x['flips'] for x in s]):.1f}")
print(f"OUR setups ({HOURS}h, {len(rows)} reconstructed) base win% {sum(1 for x in rows if x['won'])/len(rows)*100:.1f}\n")
print("=== FULL: win% by pre-entry flips ===")
rep([x for x in rows if x["flips"]<=6],"clean <=6"); rep([x for x in rows if 7<=x["flips"]<=9],"medium 7-9"); rep([x for x in rows if x["flips"]>=10],"choppy >=10")
print("\n=== binary: very-clean(<=6) vs rest(>=7) ===")
rep([x for x in rows if x["flips"]<=6],"clean <=6"); rep([x for x in rows if x["flips"]>=7],"rest >=7")
cut=rows[int(len(rows)*0.6)]["ws"]
print("\n=== HELD-OUT split (does clean>rest hold OOS?) ===")
for nm,sub in (("TRAIN",[x for x in rows if x['ws']<cut]),("HELD-OUT",[x for x in rows if x['ws']>=cut])):
    print(f"  {nm}:"); rep([x for x in sub if x["flips"]<=6],"  clean <=6"); rep([x for x in sub if x["flips"]>=7],"  rest >=7")
print("\nREAD: signal real & robust if clean<=6 beats rest in BOTH train & held-out by a similar margin.")
