"""bt_vol_pause.py — should we PAUSE all entries when btc_vol is high? Net-PnL test on REAL fills.
For each real fill (z-maker+taker), compute btc_vol30 at its window. Then: net PnL by vol bucket, and
for each pause-threshold X, the PnL of trades that would be PAUSED (vol>=X) = what we'd forgo. If that sum
is NEGATIVE, pausing helps; the more negative, the better the pause. Also reports wins forgone (a +EV
high-vol regime should NOT be paused)."""
import json, re, math, time, statistics as st, httpx
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
F = []
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl", encoding="utf-8") if l.strip()):
    if o.get("kind") == "entry" and o.get("won") is not None and o.get("pnl") is not None:
        m = re.search(r"-5m-(\d+)", o.get("slug", ""));
        if m: F.append({"ws": int(m.group(1)), "won": bool(o["won"]), "pnl": float(o["pnl"]), "eng": "taker"})
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None and o.get("pnl") is not None:
        m = re.search(r"-5m-(\d+)", o.get("slug", ""));
        if m: F.append({"ws": int(m.group(1)), "won": bool(o["won"]), "pnl": float(o["pnl"]), "eng": "zmk"})
F.sort(key=lambda x: x["ws"])
t0 = min(f["ws"] for f in F)-2400; t1 = max(f["ws"] for f in F)+600
print("fetching btc 1m...")
BTC = {}; cur = t0
with httpx.Client() as c:
    while cur < t1:
        r = c.get("https://api.binance.com/api/v3/klines", params={"symbol": "BTCUSDT", "interval": "1m", "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
        if not isinstance(r, list) or not r: break
        for k in r: BTC[int(k[0]//1000)] = float(k[4])
        cur = int(r[-1][0]//1000)+60
def vol(ws):
    m0 = ws//60*60; cl = [BTC[m0-i*60] for i in range(31) if (m0-i*60) in BTC]
    if len(cl) < 20: return None
    rr = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]; return st.pstdev(rr)
for f in F: f["v"] = vol(f["ws"])
F = [f for f in F if f["v"] is not None]
tot = sum(f["pnl"] for f in F)
print(f"{len(F)} fills, total realized ${tot:.2f}\n")
print("=== net PnL by btc_vol bucket ===")
for lo, hi in ((0, 4), (4, 5.5), (5.5, 6.5), (6.5, 8), (8, 9), (9, 99)):
    s = [f for f in F if lo <= f["v"] < hi]
    if s:
        w = sum(1 for f in s if f["won"]); p = sum(f["pnl"] for f in s)
        print(f"  vol [{lo:>4},{hi:>4}): n={len(s):4d} win%={w/len(s)*100:5.1f} netPnL=${p:+8.2f} (${p/len(s):+.3f}/fill)")
print("\n=== PAUSE simulation: skip all entries with btc_vol>=X ===")
print(f"  {'X':>4s} {'paused_n':>9s} {'paused_PnL':>11s} {'kept_PnL':>9s} {'delta_if_pause':>15s}")
for X in (5.5, 6, 6.5, 7, 8, 9):
    paused = [f for f in F if f["v"] >= X]; kept = [f for f in F if f["v"] < X]
    pp = sum(f["pnl"] for f in paused); kp = sum(f["pnl"] for f in kept)
    pw = sum(1 for f in paused if f["won"])
    print(f"  {X:>4} {len(paused):9d} ${pp:+10.2f} ${kp:+8.2f} {('+$%.2f'%(-pp)):>15s}  (paused win%={pw/len(paused)*100 if paused else 0:.0f})")
print("\nREAD: 'delta_if_pause' = PnL gained by pausing (= -paused_PnL). >0 means the paused high-vol trades")
print("were net-LOSING so skipping them helps. But check paused win%: if it's high, we'd forgo many winners.")
print("Threshold where paused_PnL is most negative = best pause point. (btc_vol misses eth-only spikes -> the")
print("breaker covers those.)")
