"""bt_regime_indicators.py — MATHEMATICIAN pass: engineer MARKET-REGIME indicators (beyond vol) and test
whether they separate our REAL winners from REAL losers, and whether the drawdown PERIOD has a distinct
regime signature. Hypothesis: vol measures AMPLITUDE; the losses cluster in a CHOPPY / mean-reverting
regime (low path-efficiency, negative return autocorrelation) that vol misses — small whippy moves that
trigger lead>=8 then reverse.

Indicators (trailing, computed at each window's start = known live):
  ER30   : Kaufman efficiency ratio of btc over trailing 30m (|net|/sum|steps|). LOW = choppy.
  AC1_60 : lag-1 autocorrelation of btc 1m returns, trailing 60m. NEGATIVE = mean-reverting (bad).
  REV20  : realized reversal rate — of the last 20 5m windows, frac whose min-3 lead sign != settle sign.
  VOL30  : btc realized vol (the existing axis, for contrast).
Outcome = REAL settle from the live fills (early_taker + z-maker). Compares win vs loss, win-rate by
bucket, and drawdown-window vs profitable-window regime."""
import json, math, time, statistics as st, httpx
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def fetch(sym, t0, t1):
    out = {}; cur = t0
    with httpx.Client() as c:
        while cur < t1:
            r = c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m",
                      "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
            if not isinstance(r, list) or not r: break
            for k in r: out[int(k[0]//1000)] = float(k[4])
            cur = int(r[-1][0]//1000)+60
    return out

# load real fills
def loadfills():
    F = []
    for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl", encoding="utf-8") if l.strip()):
        if o.get("kind") == "entry" and o.get("won") is not None:
            import re; m = re.search(r"-5m-(\d+)", o.get("slug", ""))
            if m: F.append({"ws": int(m.group(1)), "won": o["won"], "coin": o.get("coin"), "eng": "taker", "pnl": o.get("pnl", 0)})
    for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()):
        if o.get("filled") is True and o.get("won") is not None:
            import re; m = re.search(r"-5m-(\d+)", o.get("slug", ""))
            if m: F.append({"ws": int(m.group(1)), "won": o["won"], "coin": o.get("coin"), "eng": "zmaker", "pnl": o.get("pnl", 0)})
    return F
F = loadfills()
t0 = min(f["ws"] for f in F)-4000; t1 = max(f["ws"] for f in F)+600
print(f"{len(F)} real fills, span {datetime.fromtimestamp(min(f['ws'] for f in F),timezone.utc)} .. {datetime.fromtimestamp(max(f['ws'] for f in F),timezone.utc)}")
print("fetching btc 1m over live span...")
BTC = fetch("BTCUSDT", t0, t1)
mins = sorted(BTC)
def px(t): return BTC.get(t//60*60)

def ER30(ws):
    seq = [BTC[ws-i*60] for i in range(30, -1, -1) if (ws-i*60) in BTC]
    if len(seq) < 20: return None
    net = abs(seq[-1]-seq[0]); path = sum(abs(seq[i]-seq[i-1]) for i in range(1, len(seq)))
    return net/path if path else 0
def AC1(ws):
    seq = [BTC[ws-i*60] for i in range(60, -1, -1) if (ws-i*60) in BTC]
    if len(seq) < 30: return None
    r = [math.log(seq[i]/seq[i-1]) for i in range(1, len(seq))]
    if len(r) < 20 or st.pstdev(r) == 0: return None
    m = sum(r)/len(r); num = sum((r[i]-m)*(r[i-1]-m) for i in range(1, len(r))); den = sum((x-m)**2 for x in r)
    return num/den if den else 0
def VOL30(ws):
    seq = [BTC[ws-i*60] for i in range(30, -1, -1) if (ws-i*60) in BTC]
    if len(seq) < 20: return None
    r = [math.log(seq[i]/seq[i-1])*1e4 for i in range(1, len(seq))]; return st.pstdev(r)

for f in F:
    f["ER30"] = ER30(f["ws"]); f["AC1"] = AC1(f["ws"]); f["VOL30"] = VOL30(f["ws"])
F = [f for f in F if f["ER30"] is not None and f["AC1"] is not None]
win = [f for f in F if f["won"]]; loss = [f for f in F if not f["won"]]
print(f"usable {len(F)} | win {len(win)} loss {len(loss)} (loss-rate {len(loss)/len(F)*100:.1f}%)\n")

def cmp(k):
    wv = [f[k] for f in win]; lv = [f[k] for f in loss]
    print(f"  {k:7s} WIN median={st.median(wv):+.3f} [{st.quantiles(wv,n=4)[0]:+.2f},{st.quantiles(wv,n=4)[2]:+.2f}]   "
          f"LOSS median={st.median(lv):+.3f} [{st.quantiles(lv,n=4)[0]:+.2f},{st.quantiles(lv,n=4)[2]:+.2f}]")
print("=== WIN vs LOSS by engineered indicator ===")
for k in ("ER30", "AC1", "VOL30"): cmp(k)

def wrbucket(k, edges):
    print(f"\n  loss-rate by {k} bucket:")
    for i in range(len(edges)+1):
        lo = edges[i-1] if i > 0 else -1e9; hi = edges[i] if i < len(edges) else 1e9
        sub = [f for f in F if lo <= f[k] < hi]
        if len(sub) >= 20:
            lr = sum(1 for f in sub if not f["won"])/len(sub)*100
            print(f"    {k} [{lo if lo>-1e8 else '-inf':>6}, {hi if hi<1e8 else 'inf':>6}): n={len(sub):4d} loss%={lr:5.1f}")
wrbucket("ER30", [0.15, 0.30, 0.50])
wrbucket("AC1", [-0.15, 0, 0.15])
wrbucket("VOL30", [4, 6.5, 9])

# drawdown window vs profitable window regime
print("\n=== regime: DRAWDOWN window vs rest ===")
# drawdown roughly 06-16 15:20 UTC onward
dd0 = int(datetime(2026, 6, 16, 15, 20, tzinfo=timezone.utc).timestamp())
dd = [f for f in F if f["ws"] >= dd0]; rest = [f for f in F if f["ws"] < dd0]
for lab, g in (("DRAWDOWN (>=06-16 15:20)", dd), ("REST (before)", rest)):
    if g:
        print(f"  {lab:26s} n={len(g):4d} loss%={sum(1 for f in g if not f['won'])/len(g)*100:5.1f} "
              f"| ER30={st.median([f['ER30'] for f in g]):.3f} AC1={st.median([f['AC1'] for f in g]):+.3f} VOL30={st.median([f['VOL30'] for f in g]):.2f}")
print("\nIF drawdown ER30 << rest, or AC1 << 0 vs rest -> the choppy/mean-reverting regime is the quantified "
      "signature vol missed. IF loss-rate rises monotonically as ER30 falls -> ER is the indicator.")
