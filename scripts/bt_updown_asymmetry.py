"""bt_updown_asymmetry.py — OOS test of the n=3 air-pocket pattern 'all losses were Down side'.
30d btc+eth, late entry (min9-14 first qualifying lead>=8 & z>=2.5), split by SIDE (Up=lead>0 vs
Down=lead<0). If Down wins materially LESS than Up on this large independent sample -> the up-drift
asymmetry is real (the cell reversal tail concentrates on Down favorites). If ~equal -> n=3 was noise."""
import math, time, statistics as st, httpx
SYMS = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
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
print("fetching 30d btc+eth...")
SER = {c: fetch(s) for c, s in SYMS.items()}

up_w = up_n = dn_w = dn_n = 0
# also overall drift: how often does close>open (Up resolves) regardless of signal?
drift_up = drift_n = 0
for coin in SYMS:
    ser = SER[coin]; ws = (t0+2400)//300*300
    while ws+300 <= t1:
        op = ser.get(ws); cl4 = ser.get(ws+240)
        if not op or not cl4: ws += 300; continue
        o = op[0]; up_win = ser[ws+240][1] >= o
        drift_up += 1 if up_win else 0; drift_n += 1
        leads = {m: (math.log(ser[ws+m*60][1]/o)*1e4 if ser.get(ws+m*60) else None) for m in range(0, 5)}
        for m in range(3, 5):  # late entry min3-4 (5m's late window)
            l = leads.get(m)
            if l is None or abs(l) < 8: continue
            m0 = ws+m*60; cl = [ser[m0-i*60][1] for i in range(31) if (m0-i*60) in ser]
            if len(cl) < 20: break
            cl = cl[::-1]; rets = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]; v = st.pstdev(rets)
            if not v or abs(l)/v < 2.5: continue
            won = ((l >= 0) == up_win)
            if l >= 0: up_w += 1 if won else 0; up_n += 1
            else: dn_w += 1 if won else 0; dn_n += 1
            break
        ws += 300
print(f"\n=== overall drift: Up resolves {drift_up/drift_n*100:.1f}% of all {drift_n} windows (>50% = up-bias) ===")
print(f"\n=== late z>=2.5 entries by SIDE (the cell-style signal) ===")
print(f"  UP-favorite (lead>0):  n={up_n:5d}  win%={up_w/up_n*100:.2f}")
print(f"  DOWN-favorite(lead<0): n={dn_n:5d}  win%={dn_w/dn_n*100:.2f}")
print(f"  asymmetry: Up - Down = {(up_w/up_n - dn_w/dn_n)*100:+.2f}pp")
print("\nIf Down win% << Up win% on this 30d sample -> n=3 'all Down' pattern is REAL (up-drift). "
      "If ~equal -> noise. (binance-resolution proxy; win% only.)")
