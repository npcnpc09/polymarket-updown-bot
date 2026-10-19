"""btc_regime_during_cluster.py — was btc CHOPPY / reversal-heavy during the loss cluster (06-18 21:00 - 06-19
00:30 UTC) vs a calm baseline? Measure 1m-return sign-flip rate (choppiness) over rolling 60m, and zoom into
the 23:45 air-pocket window at 1s to show the whipsaw. Reversal-heavy regime = the loss-cluster signature."""
import httpx, math, time
SYM="BTCUSDT"
def klines(interval, t0, t1):
    out=[]; t=t0
    with httpx.Client(timeout=20) as c:
        while t<t1:
            k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM,"interval":interval,"startTime":t*1000,"endTime":t1*1000,"limit":1000}).json()
            if not isinstance(k,list) or not k: break
            for r in k: out.append((r[0]//1000,float(r[1]),float(r[4])))  # ts,open,close
            t=k[-1][0]//1000 + (1 if interval=="1s" else 60)
            if len(k)<1000: break
    return out
def flip_rate(rets):
    sg=[1 if x>=0 else -1 for x in rets]
    return sum(1 for i in range(1,len(sg)) if sg[i]!=sg[i-1])/(len(sg)-1) if len(sg)>1 else 0
# cluster window vs a calm baseline (same length, ~12h earlier when wallet was climbing)
cluster=(1781827200-3600*2, 1781827200+3600)   # ~06-18 21:00 - 00:30 UTC (around the air-pocket 23:45/ws1781826300+)
calm   =(1781827200-3600*14, 1781827200-3600*11)# ~12h earlier (the +$23 climb period)
for lab,(a,b) in (("CLUSTER (loss segment)",cluster),("CALM baseline (~12h earlier, climb)",calm)):
    k=klines("1m",a,b)
    rets=[math.log(k[i][2]/k[i-1][2])*1e4 for i in range(1,len(k))]
    closes=[x[2] for x in k]
    net=math.log(closes[-1]/closes[0])*1e4 if closes else 0
    rng=(max(closes)-min(closes)) if closes else 0
    import statistics as st
    print(f"=== {lab}: {len(k)} 1m-bars ===")
    print(f"   flip-rate(1m sign-changes)={flip_rate(rets):.2f}  |  1m-vol(stdev bps)={st.pstdev(rets):.1f}  |  net move={net:+.0f}bps  range=${rng:.0f}")
# zoom: the air-pocket window at 1s (ws 1781826300 = the -18.20 btc Down 20sh, settle +300)
print("\n=== AIR-POCKET window 1781826300 (btc Down 20sh -$18.20) at 1s — the whipsaw ===")
aw=klines("1s",1781826300,1781826300+300)
if aw:
    opn=aw[0][1]
    for off in (0,30,60,90,120,150,180,210,240,299):
        idx=min(off,len(aw)-1)
        print(f"   off={off:4d}s  px={aw[idx][2]:.2f}  lead={math.log(aw[idx][2]/opn)*1e4:+.1f}bps")
    # count direction changes within the window (5s-bucketed)
    buck=[aw[i][2] for i in range(0,len(aw),5)]
    br=[1 if buck[i]>=buck[i-1] else -1 for i in range(1,len(buck))]
    nflip=sum(1 for i in range(1,len(br)) if br[i]!=br[i-1])
    print(f"   within-window direction flips (5s-bucketed): {nflip}  (we bet Down lead-6.4; it reversed UP -> lost)")
print("\nREAD: high flip-rate + low net move = choppy/reversal regime. If the cluster window is clearly")
print("choppier than the calm baseline, the user's read holds: losses cluster in btc's reversal-heavy segments.")
