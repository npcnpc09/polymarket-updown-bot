"""bt_adverse_regime_prevalence.py — how much of the past month was a 'loss-concentrated regime' like the
last 2 days? 30d eth+btc, per 6h block: avg vol (1m ret stdev) + reversal rate (|lead@min3|>=8 windows
whose settle-sign flips). Reference = the last-2-days blocks. Count blocks at/above that adverse level."""
import math, time, statistics as st, httpx
from datetime import datetime, timezone
SYMS = {"eth": "ETHUSDT", "btc": "BTCUSDT"}
now = int(time.time()); t1 = now//60*60; t0 = t1 - 30*86400 - 2400
def fetch(sym):
    out = {}; cur = t0
    with httpx.Client() as c:
        while cur < t1:
            r = c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
            if not isinstance(r, list) or not r: break
            for k in r: out[int(k[0]//1000)] = (float(k[1]), float(k[4]))
            cur = int(r[-1][0]//1000)+60
    return out
print("fetching 30d eth+btc...")
SER = {c: fetch(s) for c, s in SYMS.items()}
BLK = 6*3600
def block(ts): return (ts//BLK)*BLK
# per 6h block per coin: vol + reversal rate (focus eth, the bleed coin)
def block_metrics(coin):
    ser = SER[coin]; vols = {}; rev = {}
    mins = sorted(ser)
    for i in range(1, len(mins)):
        if mins[i]-mins[i-1] == 60:
            b = block(mins[i]); vols.setdefault(b, []).append(math.log(ser[mins[i]][1]/ser[mins[i-1]][1])*1e4)
    ws = (t0//300)*300
    while ws+300 <= t1:
        o = ser.get(ws); c3 = ser.get(ws+180); c4 = ser.get(ws+240)
        if o and c3 and c4:
            lead3 = math.log(c3[1]/o[0])*1e4; settle = math.log(c4[1]/o[0])*1e4
            if abs(lead3) >= 8:
                b = block(ws); rev.setdefault(b, [0, 0]); rev[b][1] += 1
                if (lead3 >= 0) != (settle >= 0): rev[b][0] += 1
        ws += 300
    blocks = {}
    for b in vols:
        if len(vols[b]) > 60:
            rv = rev.get(b, [0, 0]); revpct = rv[0]/rv[1]*100 if rv[1] >= 5 else None
            blocks[b] = {"vol": st.pstdev(vols[b]), "rev": revpct, "nrev": rv[1]}
    return blocks

eb = block_metrics("eth")
allblocks = sorted(eb)
# reference = last 2 days blocks (06-16 00:00 .. now)
ref0 = int(datetime(2026, 6, 16, 0, 0, tzinfo=timezone.utc).timestamp())
last2 = [eb[b] for b in allblocks if b >= ref0]
ref_vol = st.median([x["vol"] for x in last2])
ref_rev = st.median([x["rev"] for x in last2 if x["rev"] is not None])
print(f"\n=== eth: last-2-days reference (median over {len(last2)} 6h-blocks) ===")
print(f"  vol={ref_vol:.2f} bps/min | reversal-rate={ref_rev:.1f}%")
# count month blocks at/above adverse level
priorblocks = [eb[b] for b in allblocks if b < ref0]
hi_vol = [x for x in priorblocks if x["vol"] >= ref_vol]
hi_rev = [x for x in priorblocks if x["rev"] is not None and x["rev"] >= ref_rev]
either = [x for x in priorblocks if x["vol"] >= ref_vol or (x["rev"] is not None and x["rev"] >= ref_rev)]
np = len(priorblocks)
print(f"\n=== prior ~28 days ({np} 6h-blocks = {np*6:.0f}h): how much matched the adverse level? ===")
print(f"  vol >= {ref_vol:.1f}:        {len(hi_vol)}/{np} blocks = {len(hi_vol)/np*100:.0f}% of time")
print(f"  reversal >= {ref_rev:.0f}%:  {len(hi_rev)}/{len([x for x in priorblocks if x['rev'] is not None])} = {len(hi_rev)/max(1,len([x for x in priorblocks if x['rev'] is not None]))*100:.0f}% of time")
print(f"  EITHER (vol OR rev adverse): {len(either)}/{np} = {len(either)/np*100:.0f}% of time")
# show the daily vol trajectory to see clustering
print(f"\n=== eth vol by day (median of 6h blocks) — where are the adverse stretches? ===")
byday = {}
for b in allblocks:
    d = datetime.fromtimestamp(b, timezone.utc).strftime("%m-%d"); byday.setdefault(d, []).append(eb[b]["vol"])
for d in sorted(byday):
    mv = st.median(byday[d]); flag = " <-- adverse" if mv >= ref_vol else ""
    print(f"  {d}: vol={mv:.2f}{flag}")
print(f"\nREAD: % of month at/above the last-2-days adverse level = how often this loss-prone regime occurs.")
