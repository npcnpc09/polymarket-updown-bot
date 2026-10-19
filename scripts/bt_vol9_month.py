"""bt_vol9_month.py — month-scale test of the btc_vol>=9 PAUSE for the z-maker.
30d btc+eth. late entry (min3-4 first qualifying lead>=8 & z>=2.5 = the z-maker signal). btc_vol30 at
entry (the gate is BTC vol for both coins). win% by btc_vol bucket; vol>=9 vs <9; pause trigger frequency.
binance settlement (relative read; real loss-rate higher on tight calls, so vol>=9 danger UNDERSTATED)."""
import math, time, statistics as st, httpx
SYMS = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
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
print("fetching 30d btc+eth...")
SER = {c: fetch(s) for c, s in SYMS.items()}
BTC = SER["btc"]
def btcvol(ws):
    m0 = ws//60*60; cl = [BTC[m0-i*60][1] for i in range(31) if (m0-i*60) in BTC]
    if len(cl) < 20: return None
    rr = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]; return st.pstdev(rr)
def ownvol(ser, ws, m):
    m0 = (ws+m*60); cl = [ser[m0-i*60][1] for i in range(31) if (m0-i*60) in ser]
    if len(cl) < 20: return None
    rr = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]; return st.pstdev(rr)
E = []
for coin in SYMS:
    ser = SER[coin]; ws = (t0+2400)//300*300
    while ws+300 <= t1:
        op = ser.get(ws); c4 = ser.get(ws+240)
        if op and c4:
            o = op[0]; up_win = c4[1] >= o
            for m in (3, 4):
                cc = ser.get(ws+m*60)
                if not cc: continue
                l = math.log(cc[1]/o)*1e4
                if abs(l) < 8: continue
                v = ownvol(ser, ws, m)
                if not v or abs(l)/v < 2.5: continue
                bv = btcvol(ws+m*60)
                if bv is None: continue
                E.append({"won": ((l >= 0) == up_win), "bv": bv}); break
        ws += 300
n = len(E); base = sum(1 for e in E if e["won"])/n*100
days = 30
print(f"\n{n} late-z>=2.5 entries over {days}d ({n/days:.0f}/day) | overall win% {base:.2f}\n")
print("=== win% by btc_vol bucket ===")
for lo, hi in ((0, 4), (4, 5.5), (5.5, 6.5), (6.5, 8), (8, 9), (9, 99)):
    s = [e for e in E if lo <= e["bv"] < hi]
    if s:
        w = sum(1 for e in s if e["won"]); print(f"  vol [{lo:>4},{hi:>4}): n={len(s):5d} ({len(s)/n*100:4.1f}%) win%={w/len(s)*100:6.2f}  loss%={100-w/len(s)*100:.2f}")
hi9 = [e for e in E if e["bv"] >= 9]; lo9 = [e for e in E if e["bv"] < 9]
print(f"\n=== vol>=9 PAUSE (the proposed gate) ===")
print(f"  vol>=9 : n={len(hi9)} ({len(hi9)/n*100:.1f}% of entries = pause fires ~{len(hi9)/days:.1f}x/day) win%={sum(1 for e in hi9 if e['won'])/len(hi9)*100:.2f}")
print(f"  vol<9  : n={len(lo9)} win%={sum(1 for e in lo9 if e['won'])/len(lo9)*100:.2f}")
print(f"  gap = {sum(1 for e in lo9 if e['won'])/len(lo9)*100 - sum(1 for e in hi9 if e['won'])/len(hi9)*100:+.2f}pp")
print("\nNOTE: binance settlement understates the real loss-rate (tight-call reversals it can't see, which")
print("cluster in high vol) -> the REAL vol>=9 danger is larger than shown (live real fills: vol>=9 = 67% win/")
print("-$36.65). If even the optimistic binance shows vol>=9 materially worse -> the pause is supported.")
