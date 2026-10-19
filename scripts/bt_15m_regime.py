"""bt_15m_regime.py — REGIME-CONDITIONAL 15m sweep. Loads bt15m_cache.json (built by bt_15m_sweep),
attaches two regime labels KNOWABLE AT ENTRY (min 9) so a live engine could switch on them:
  VOL  : BTC vol30 at min9  -> calm(<6.5) / volatile(>=6.5)   [the OOS-validated gate]
  PATH : lead flips & persistence by min9 -> trend / chop
Then runs the strategy grid WITHIN each regime + reports the no-op baseline (does the leading side
just win in that regime?). Goal: a regime->strategy map, not one global config.
Fetches BTC 1m klines ONCE globally (paginated) to get btc_vol per minute."""
import json, math, os, sys, httpx, statistics as st, itertools
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
CACHE = ROOT + "/data/bt15m_cache.json"
data = json.load(open(CACHE))
for d in data:
    d["leads"] = {int(k): v for k, v in d["leads"].items()}
    d["vols"] = {int(k): v for k, v in d["vols"].items()}
    d["prices"] = {int(k): v for k, v in d["prices"].items()}
data = sorted(data, key=lambda d: d["start"])
print(f"loaded {len(data)} windows")

# ---- global BTC 1m close series -> btc_vol30 per minute ----
t0 = min(d["start"] for d in data) - 2400
t1 = max(d["start"] for d in data) + 1200
btc_close = {}
cur = t0
with httpx.Client() as c:
    while cur < t1:
        r = c.get("https://api.binance.com/api/v3/klines",
                  params={"symbol": "BTCUSDT", "interval": "1m", "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
        if not isinstance(r, list) or not r: break
        for k in r: btc_close[int(k[0]//1000)] = float(k[4])
        cur = int(r[-1][0]//1000) + 60
print(f"btc minutes fetched: {len(btc_close)}")
def btc_vol_at(ts):
    m0 = ts//60*60
    cl = [btc_close[m0-i*60] for i in range(31) if (m0-i*60) in btc_close]
    if len(cl) < 20: return None
    cl = cl[::-1]; rets = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]
    return st.pstdev(rets)

# ---- attach regime labels at min9 ----
RCM = 9  # regime-classification minute
for d in data:
    L = d["leads"]
    seq = [L[m] for m in range(1, RCM+1) if L.get(m) is not None]
    flips = sum(1 for i in range(1, len(seq)) if (seq[i] >= 0) != (seq[i-1] >= 0)) if len(seq) > 1 else 0
    pk = max((abs(x) for x in seq), default=0.0)
    persist = (abs(seq[-1])/pk) if (seq and pk > 0) else 0.0
    bv = btc_vol_at(d["start"] + RCM*60)
    d["bv9"] = bv
    d["vol_reg"] = ("calm" if (bv is not None and bv < 6.5) else "volatile") if bv is not None else "unk"
    d["path_reg"] = "trend" if (flips <= 1 and persist >= 0.7) else "chop"
    d["flips9"] = flips; d["persist9"] = round(persist, 2)

# ---- strategy grid (same space as sweep) ----
TIMING = {"early": range(1, 7), "mid": range(6, 12), "late": range(9, 15), "any": range(1, 15)}
BANDS = {"any": (0.30, 0.96), "cheap": (0.30, 0.66), "mid": (0.55, 0.86), "fav": (0.80, 0.96), "cell": (0.90, 0.96)}
def run(strat, rows):
    tmin, lead_thr, z_thr, ml_thr, band = strat
    lo, hi = BANDS[band]; fills = []
    for d in rows:
        L, V, P = d["leads"], d["vols"], d["prices"]
        for m in TIMING[tmin]:
            l = L.get(m)
            if l is None: continue
            pk = max((abs(L[mm]) for mm in range(0, m+1) if L.get(mm) is not None), default=0.0)
            if abs(l) < lead_thr: continue
            v = V.get(m)
            if z_thr > 0 and (not v or abs(l)/v < z_thr): continue
            if ml_thr > 0 and pk < ml_thr: continue
            p = P.get(m)
            if p is None: continue
            B = round(min(p+0.01, 0.97), 2)
            if not (lo <= B < hi): continue
            won = ((l >= 0) == d["up_win"]); sh = 20 if (0.90 <= B < 0.95) else 5
            fills.append((B, won, sh)); break
    if not fills: return None
    n = len(fills); w = sum(1 for f in fills if f[1])
    pnl = sum(((1-b) if won else -b)*s for b, won, s in fills)
    return {"n": n, "win": w/n, "ev": pnl/n, "cov": n/len(rows)}

grid = list(itertools.product(["mid", "late", "any"], [8], [0, 2.0, 2.5, 3.0], [0, 15, 20], ["any", "mid", "fav", "cell"]))

# ---- per-regime analysis ----
def baseline(rows):
    # no-op: leading side at min10, late, any price -> win rate (does regime itself predict?)
    w = n = 0
    for d in rows:
        l = d["leads"].get(10)
        if l is None or abs(l) < 8: continue
        n += 1; w += ((l >= 0) == d["up_win"])
    return (w/n, n) if n else (0, 0)

regimes = {
    "ALL": data,
    "calm": [d for d in data if d["vol_reg"] == "calm"],
    "volatile": [d for d in data if d["vol_reg"] == "volatile"],
    "trend": [d for d in data if d["path_reg"] == "trend"],
    "chop": [d for d in data if d["path_reg"] == "chop"],
    "calm+trend": [d for d in data if d["vol_reg"] == "calm" and d["path_reg"] == "trend"],
    "calm+chop": [d for d in data if d["vol_reg"] == "calm" and d["path_reg"] == "chop"],
    "volatile+trend": [d for d in data if d["vol_reg"] == "volatile" and d["path_reg"] == "trend"],
    "volatile+chop": [d for d in data if d["vol_reg"] == "volatile" and d["path_reg"] == "chop"],
}
print("\nregime sizes:", {k: len(v) for k, v in regimes.items()})

for rname, rows in regimes.items():
    if len(rows) < 25:
        print(f"\n### {rname} (n={len(rows)}) — too small, skip"); continue
    # time-split within regime
    cut = int(len(rows)*0.6); tr, te = rows[:cut], rows[cut:]
    bw, bn = baseline(rows)
    print(f"\n### REGIME {rname} (n={len(rows)}, base lead-side win={bw*100:.0f}%/{bn}) ===")
    cand = []
    for s in grid:
        rT = run(s, tr); rE = run(s, te)
        if not rT or not rE or rT["n"] < 8 or rE["n"] < 6: continue
        if abs(rT["win"]-rE["win"]) > 0.12: continue  # OOS guard
        cand.append((s, rT, rE))
    # rank by test win% then coverage
    for s, rT, rE in sorted(cand, key=lambda x: (x[2]["win"], x[2]["cov"]), reverse=True)[:4]:
        tag = f"{s[0]}/z{s[2]}/ml{s[3]}/{s[4]}"
        print(f"   {tag:24s} TRAIN {rT['n']:3d}/{rT['win']*100:3.0f}%  TEST {rE['n']:3d}/{rE['win']*100:3.0f}%/"
              f"ev{rE['ev']:+.2f}  cov{rE['cov']*100:2.0f}%")
print("\nNOTE: assume-fill EV optimistic; rank on TEST win + coverage + small gap. Baseline = does the "
      "regime alone predict the leading side winning (if base is already ~high, strategy adds little).")
