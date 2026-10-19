"""bt_eth_ownvol_time.py — INDEPENDENT backtest of eth-specific treatments (drawdown hypothesis:
eth loses in US afternoon when btc is calm but eth own-vol is elevated). 30d eth, late entry (min3-4,
lead>=8 & z>=2.5 = cell-eligible). Tests: (a) eth own-vol gate, (b) btc-vol gate (current), (c) the
cross btc-calm x eth-own-vol-high (the exact drawdown setup), (d) hour-of-day. win% is the metric (cell
at ~0.92 => breakeven 92%; <92% => gate helps). Challenges memory's 'own-vol gating drops winners'."""
import math, time, statistics as st, httpx
from datetime import datetime, timezone
now = int(time.time()); t1 = now//60*60; t0 = t1 - 30*86400 - 2400
def fetch(sym):
    out = {}; cur = t0
    with httpx.Client() as c:
        while cur < t1:
            r = c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m",
                      "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
            if not isinstance(r, list) or not r: break
            for k in r: out[int(k[0]//1000)] = (float(k[1]), float(k[4]))
            cur = int(r[-1][0]//1000)+60
    return out
print("fetching 30d eth+btc...")
ETH = fetch("ETHUSDT"); BTC = fetch("BTCUSDT")
def vol_at(ser, ts):
    m0 = ts//60*60; cl = [ser[m0-i*60][1] for i in range(31) if (m0-i*60) in ser]
    if len(cl) < 20: return None
    cl = cl[::-1]; rets = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]; return st.pstdev(rets)

E = []
ws = (t0+2400)//300*300
while ws+300 <= t1:
    op = ETH.get(ws); c4 = ETH.get(ws+240)
    if not op or not c4: ws += 300; continue
    o = op[0]; up_win = ETH[ws+240][1] >= o
    leads = {m: (math.log(ETH[ws+m*60][1]/o)*1e4 if ETH.get(ws+m*60) else None) for m in range(0, 5)}
    for m in range(3, 5):
        l = leads.get(m)
        if l is None or abs(l) < 8: continue
        ev = vol_at(ETH, ws+m*60);
        if not ev or abs(l)/ev < 2.5: continue
        bv = vol_at(BTC, ws+m*60)
        E.append({"won": ((l >= 0) == up_win), "ethvol": ev, "btcvol": bv if bv else 0,
                  "hour": datetime.fromtimestamp(ws, timezone.utc).hour, "side": "Up" if l >= 0 else "Down"})
        break
    ws += 300
n = len(E); base = sum(1 for e in E if e["won"])/n*100
print(f"\neth cell-eligible entries: {n} | base win% = {base:.2f}  (cell @~0.92 => need >92% for +EV)\n")

def wr(rows, lab):
    if not rows: print(f"  {lab:34s} n=0"); return
    w = sum(1 for e in rows if e["won"]); print(f"  {lab:34s} n={len(rows):5d} win%={w/len(rows)*100:5.2f}  {'(+EV)' if w/len(rows)*100>=92 else '(-EV)'}")

print("=== (b) BTC-vol gate (current, the validated one) ===")
wr([e for e in E if e["btcvol"] < 6.5], "btc_vol<6.5 (KEEP)")
wr([e for e in E if e["btcvol"] >= 6.5], "btc_vol>=6.5 (current SKIP)")
print("\n=== (a) ETH own-vol gate ===")
for x in (6.5, 8, 10, 12):
    wr([e for e in E if e["ethvol"] < x], f"eth_vol<{x} (KEEP)")
    wr([e for e in E if e["ethvol"] >= x], f"eth_vol>={x} (would SKIP)")
print("\n=== (c) THE DRAWDOWN SETUP: btc calm (<6.5) x eth own-vol high ===")
calm = [e for e in E if e["btcvol"] < 6.5]
print(f"  within btc-calm (n={len(calm)}):")
for x in (6.5, 8, 10):
    wr([e for e in calm if e["ethvol"] >= x], f"  btc<6.5 AND eth_vol>={x}")
wr([e for e in calm if e["ethvol"] < 6.5], "  btc<6.5 AND eth_vol<6.5")
print("\n=== (d) hour-of-day (UTC), esp 18-20 ===")
for h in range(0, 24):
    rows = [e for e in E if e["hour"] == h]
    if len(rows) >= 15:
        w = sum(1 for e in rows if e["won"]); flag = " <--US-aft" if 18 <= h <= 20 else ""
        mark = " LOW" if w/len(rows)*100 < base-3 else ""
        print(f"  {h:02d}:00 n={len(rows):4d} win%={w/len(rows)*100:5.2f}{mark}{flag}")
print("\n=== gate cost: eth_vol>=8 skip — losses avoided vs winners cut ===")
sk = [e for e in E if e["ethvol"] >= 8]; skl = sum(1 for e in sk if not e["won"]); skw = sum(1 for e in sk if e["won"])
print(f"  eth_vol>=8 skips {len(sk)} ({skw} WIN + {skl} LOSS). loss-rate in skipped {skl/len(sk)*100:.1f}% vs base {(100-base):.1f}%")
print("\nVERDICT logic: a gate helps ONLY if the skipped bucket is <92% win (cell -EV there) AND it doesn't "
      "skip mostly winners. If btc-calm x eth-high-vol still wins >92% -> memory holds, drawdown was variance.")
