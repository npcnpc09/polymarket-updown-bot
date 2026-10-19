"""bt_market_regime_byday.py — daily market-regime metrics btc/eth/sol, 06-12..now, to compare the
06-13 era vs the last 2 days. Per UTC day per coin: VOL (1m ret stdev bps/min), |ret| mean, ER (5m
efficiency), REV% (5m windows |early-lead|>=8, early-sign != settle-sign)."""
import math, time, statistics as st, httpx
from datetime import datetime, timezone
SYMS = {"btc": "BTCUSDT", "eth": "ETHUSDT", "sol": "SOLUSDT"}
t1 = int(time.time())//60*60
t0 = int(datetime(2026, 6, 12, 0, 0, tzinfo=timezone.utc).timestamp())
def fetch(sym):
    out = {}; cur = t0
    with httpx.Client() as c:
        while cur < t1:
            r = c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
            if not isinstance(r, list) or not r: break
            for k in r: out[int(k[0]//1000)] = (float(k[1]), float(k[4]))
            cur = int(r[-1][0]//1000)+60
    return out
print("fetching 06-12..now btc/eth/sol...")
SER = {c: fetch(s) for c, s in SYMS.items()}
def day(ts): return datetime.fromtimestamp(ts, timezone.utc).strftime("%m-%d")
for coin in SYMS:
    ser = SER[coin]; mins = sorted(ser)
    # group 1m returns by day
    byday = {}
    for i in range(1, len(mins)):
        if mins[i]-mins[i-1] == 60:
            r = math.log(ser[mins[i]][1]/ser[mins[i-1]][1])*1e4
            byday.setdefault(day(mins[i]), []).append(r)
    # 5m windows by day: ER + reversal
    erday = {}; revday = {}
    ws = (t0//300)*300
    while ws+300 <= t1:
        seq = [ser[ws+k*60][1] for k in range(0, 6) if (ws+k*60) in ser]
        if len(seq) >= 5:
            d = day(ws); net = abs(seq[-1]-seq[0]); path = sum(abs(seq[i]-seq[i-1]) for i in range(1, len(seq)))
            if path: erday.setdefault(d, []).append(net/path)
            o = seq[0]; early = math.log(seq[min(2, len(seq)-1)]/o)*1e4; settle = math.log(seq[-1]/o)*1e4
            if abs(early) >= 8:
                revday.setdefault(d, [0, 0]); revday[d][1] += 1
                if (early >= 0) != (settle >= 0): revday[d][0] += 1
        ws += 300
    print(f"\n=== {coin.upper()} by day ===")
    print(f"  {'day':6s} {'VOL':>6s} {'|ret|':>6s} {'ER':>6s} {'REV%':>6s} {'nWin':>5s}")
    for d in sorted(byday):
        rets = byday[d]; vol = st.pstdev(rets) if len(rets) > 10 else 0
        ar = sum(abs(x) for x in rets)/len(rets) if rets else 0
        er = sum(erday.get(d, [0]))/len(erday[d]) if erday.get(d) else 0
        rv = revday.get(d, [0, 0]); revpct = rv[0]/rv[1]*100 if rv[1] else 0
        print(f"  {d:6s} {vol:6.2f} {ar:6.2f} {er:6.3f} {revpct:5.1f}% {rv[1]:5d}")
print("\n(06-13 era = 06-12/13/14 ; last 2 days = 06-16/17. Higher VOL/|ret| = bigger swings; lower ER /")
print(" higher REV% = choppier/more reversals = harder for our directional maker.)")
