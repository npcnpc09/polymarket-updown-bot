"""bt_regime_strategy_map.py — DIFFERENTIATING analysis: which regime favors EARLY vs LATE entry?
Hypothesis: EARLY entry (early_maker: bet the lead persists) needs a TRENDING regime; LATE/cell entry
(bet the developed favorite holds) is more robust to chop. 30d btc+eth. Ex-ante regime = trailing-30m
Kaufman efficiency ratio (ER) at window start (HIGH=trending, LOW=choppy). For each window compute:
  EARLY: bet sign(lead@min3) [|lead@min3|>=8]  -> win = settle matches
  LATE : bet sign(lead@min9) [|lead@min9|>=8]  -> win = settle matches
win% by trailing-ER bucket. If EARLY win% climbs steeply with ER but LATE stays flat-high -> EARLY is the
trend-conditional strategy, LATE is regime-robust = the differentiation."""
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
def trailing_ER(ser, ws):  # efficiency ratio of prior 30 1m closes
    m0 = ws//60*60; cl = [ser[m0-i*60][1] for i in range(30, -1, -1) if (m0-i*60) in ser]
    if len(cl) < 20: return None
    net = abs(cl[-1]-cl[0]); path = sum(abs(cl[i]-cl[i-1]) for i in range(1, len(cl)))
    return net/path if path else 0
EARLY = []; LATE = []  # (ER, won)
for coin in SYMS:
    ser = SER[coin]; ws = (t0+2400)//300*300
    while ws+300 <= t1:
        op = ser.get(ws); c4 = ser.get(ws+240)
        if op and c4:
            o = op[0]; settle = math.log(c4[1]/o)*1e4
            er = trailing_ER(ser, ws)
            if er is not None:
                c1 = ser.get(ws+60); c3 = ser.get(ws+180)
                if c1:
                    le = math.log(c1[1]/o)*1e4   # min1 ~ early
                    if abs(le) >= 8: EARLY.append((er, (le >= 0) == (settle >= 0)))
                if c3:
                    ll = math.log(c3[1]/o)*1e4   # min3 ~ late-ish (5m late)
                    if abs(ll) >= 8: LATE.append((er, (ll >= 0) == (settle >= 0)))
        ws += 300
def by_er(rows, lab):
    print(f"\n  {lab} win% by trailing-ER (regime):")
    for lo, hi, t in ((0, 0.2, "very choppy"), (0.2, 0.35, "choppy"), (0.35, 0.55, "mixed"), (0.55, 1.01, "trending")):
        s = [(e, w) for e, w in rows if lo <= e < hi]
        if len(s) >= 20:
            wn = sum(1 for e, w in s if w)
            print(f"    ER[{lo:.2f},{hi:.2f}] {t:11s}: n={len(s):5d} win%={wn/len(s)*100:5.1f}")
print(f"\nEARLY entries(min1, |lead|>=8): {len(EARLY)} | LATE entries(min3): {len(LATE)}")
by_er(EARLY, "EARLY (bet lead persists)")
by_er(LATE, "LATE (bet developed favorite)")
# the spread = trend-sensitivity
def spread(rows):
    ch = [w for e, w in rows if e < 0.2]; tr = [w for e, w in rows if e >= 0.55]
    if ch and tr: return sum(tr)/len(tr)*100 - sum(ch)/len(ch)*100
    return None
print(f"\n  trend-sensitivity (trending win% - very-choppy win%): EARLY={spread(EARLY):+.1f}pp  LATE={spread(LATE):+.1f}pp")
print("\nREAD: bigger EARLY spread = early entry is more regime-conditional (needs trend). If LATE spread is")
print("small, late/cell is the regime-robust strategy -> use EARLY only when trend is detected, LATE always.")
