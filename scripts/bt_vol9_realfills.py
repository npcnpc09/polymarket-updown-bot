"""bt_vol9_realfills.py — month-scale REAL-settlement test of the btc_vol>=9 pause.
alltrader_fills_real.json = real btc/eth fills with REAL won (settlement). Filter to ~our entry profile
(favorite band 0.85-0.97, |lead|>=8, late off>=120), compute btc_vol30 at each window, bucket -> REAL win%.
This is the proper test (binance-reconstruction backtest was blind to high-vol losses)."""
import json, math, statistics as st, httpx
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
print("loading alltrader_fills_real.json...")
fills = json.load(open(ROOT+"/data/alltrader_fills_real.json"))
print(f"  {len(fills)} total fills")
# filter to our entry profile
sel = []
for f in fills:
    p = f.get("price"); ld = f.get("lead"); off = f.get("off"); won = f.get("won")
    if p is None or ld is None or won is None: continue
    if 0.85 <= p <= 0.97 and abs(ld) >= 8 and (off is None or off >= 120):
        import re; m = re.search(r"-5m-(\d+)", f.get("slug", ""))
        if m: sel.append({"ws": int(m.group(1)), "won": bool(won), "p": p})
print(f"  {len(sel)} fills match profile (favorite 0.85-0.97, |lead|>=8, late)")
wss = sorted(set(s["ws"] for s in sel))
print(f"  {len(wss)} unique windows, span days={(wss[-1]-wss[0])/86400:.1f}")
# fetch btc klines covering the range
t0 = wss[0]-2400; t1 = wss[-1]+400
print("fetching btc 1m over range...")
BTC = {}; cur = t0
with httpx.Client() as c:
    while cur < t1:
        r = c.get("https://api.binance.com/api/v3/klines", params={"symbol": "BTCUSDT", "interval": "1m", "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
        if not isinstance(r, list) or not r: break
        for k in r: BTC[int(k[0]//1000)] = float(k[4])
        cur = int(r[-1][0]//1000)+60
print(f"  btc minutes: {len(BTC)}")
volcache = {}
def btcvol(ws):
    key = ws//60*60
    if key in volcache: return volcache[key]
    cl = [BTC[key-i*60] for i in range(31) if (key-i*60) in BTC]
    v = None
    if len(cl) >= 20:
        rr = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]; v = st.pstdev(rr)
    volcache[key] = v; return v
for s in sel: s["bv"] = btcvol(s["ws"])
sel = [s for s in sel if s["bv"] is not None]
n = len(sel); base = sum(1 for s in sel if s["won"])/n*100
print(f"\n{n} real fills with vol | overall REAL win% = {base:.2f}\n")
print("=== REAL win% by btc_vol bucket (real settlement) ===")
for lo, hi in ((0, 4), (4, 5.5), (5.5, 6.5), (6.5, 8), (8, 9), (9, 99)):
    s = [x for x in sel if lo <= x["bv"] < hi]
    if s:
        w = sum(1 for x in s if x["won"]); print(f"  vol [{lo:>4},{hi:>4}): n={len(s):6d} win%={w/len(s)*100:6.2f}  loss%={100-w/len(s)*100:.2f}")
hi9 = [s for s in sel if s["bv"] >= 9]; lo9 = [s for s in sel if s["bv"] < 9]
w9 = sum(1 for s in hi9 if s["won"])/len(hi9)*100; wl = sum(1 for s in lo9 if s["won"])/len(lo9)*100
print(f"\n  vol>=9: n={len(hi9)} ({len(hi9)/n*100:.1f}%) REAL win%={w9:.2f}")
print(f"  vol<9 : n={len(lo9)} REAL win%={wl:.2f}  |  gap={wl-w9:+.2f}pp")
# EV at favorite band ~0.91: breakeven win = 91%
print(f"\n  at avg favorite price ~0.91, breakeven win%~91 -> vol>=9 win {w9:.0f}% is {'+EV' if w9>=91 else '-EV'}, vol<9 {wl:.0f}% {'+EV' if wl>=91 else '-EV'}")
