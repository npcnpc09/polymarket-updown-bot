"""bt_15m_sweep.py — sweep MANY 15m maker strategies over the SAME real windows, rank by win%/EV,
with a TIME-SPLIT train/test guard against overfit (the winner of a big grid is usually the luckiest
config — only OOS-robust configs count). Phase1: fetch each window's full trajectory ONCE -> cache.
Phase2: run the grid in-memory over cached trajectories.

Strategy space (directional maker, leading side, single first-qualifying entry):
  timing  : window-minute range to look for entry   (early/mid/late/any)
  lead_thr: min |lead| at entry (bps)
  z_thr   : min z=|lead|/vol30                       (0=off)
  ml_thr  : min peak |lead| seen so far              (0=off)
  band    : entry-price band (maker B=price+0.01)
Fill model = assume-fill (data has only mid price; fill quality is UNRESOLVABLE here -> rank on win%)."""
import json, math, os, sys, httpx, statistics as st, itertools
from concurrent.futures import ThreadPoolExecutor
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
BSYM = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
CACHE = ROOT + "/data/bt15m_cache.json"

def build_cache(nper):
    wins = []
    for ln in open(ROOT + "/data/updown_tokens.jsonl", encoding="utf-8"):
        try: r = json.loads(ln)
        except: continue
        if r.get("dur") == 900 and r.get("coin") in BSYM: wins.append(r)
    wins = sorted(wins, key=lambda r: r["start"])[-nper:]
    print(f"fetching {len(wins)} windows...")
    def bn(sym, t0, t1):
        out = {}
        try:
            r = httpx.get("https://api.binance.com/api/v3/klines",
                          params={"symbol": sym, "interval": "1m", "startTime": t0*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
            for k in r:
                if isinstance(k, list): out[int(k[0]//1000)] = (float(k[1]), float(k[4]))
        except: pass
        return out
    def ph(tok, st_):
        try:
            r = httpx.get("https://clob.polymarket.com/prices-history",
                          params={"market": tok, "startTs": st_-120, "endTs": st_+900+180, "fidelity": "1"}, timeout=15).json()
            h = r.get("history", []) if isinstance(r, dict) else []
            return {int(x["t"]//60): float(x["p"]) for x in h}
        except: return {}
    def job(w):
        coin, st_, settle, up = w["coin"], w["start"], w["settle"], w["up"]
        bnd = bn(BSYM[coin], st_-1860, settle+120)
        if st_ not in bnd: return None
        op = bnd[st_][0]
        h = ph(up, st_)
        if len(h) < 5: return None
        m0 = st_//60
        up_win = h[max(h)] >= 0.5
        leads, vols, prices = {}, {}, {}
        for m in range(0, 15):  # window minute 0..14
            c = bnd.get((m0+m)*60)
            leads[m] = round(math.log(c[1]/op)*1e4, 2) if c else None
            cl = [bnd[(m0+m-i)*60][1] for i in range(31) if (m0+m-i)*60 in bnd]
            if len(cl) >= 20:
                cl = cl[::-1]; rets = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]
                vols[m] = round(st.pstdev(rets), 3)
            else: vols[m] = None
            pr = None
            for d in range(0, 4):
                if (m0+m-d) in h: pr = h[m0+m-d]; break
            prices[m] = pr
        return {"coin": coin, "start": st_, "up_win": up_win, "leads": leads, "vols": vols, "prices": prices}
    data = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for i, r in enumerate(ex.map(job, wins)):
            if r: data.append(r)
            if i % 100 == 0: print(f"  {i}/{len(wins)}")
    json.dump(data, open(CACHE, "w"))
    print(f"cached {len(data)} windows -> {CACHE}")
    return data

# ---- load/build cache ----
if "--rebuild" in sys.argv or not os.path.exists(CACHE):
    nper = int(sys.argv[sys.argv.index("--n")+1]) if "--n" in sys.argv else 580
    data = build_cache(nper)
else:
    data = json.load(open(CACHE))
    data = [{**d, "leads": {int(k): v for k, v in d["leads"].items()},
             "vols": {int(k): v for k, v in d["vols"].items()},
             "prices": {int(k): v for k, v in d["prices"].items()}} for d in data]
    print(f"loaded {len(data)} cached windows")

# time split: train = earliest 60%, test = latest 40%
data = sorted(data, key=lambda d: d["start"])
cut = int(len(data)*0.6)
TRAIN, TEST = data[:cut], data[cut:]

TIMING = {"early": range(1, 7), "mid": range(6, 12), "late": range(9, 15), "any": range(1, 15)}
BANDS = {"any": (0.30, 0.96), "cheap": (0.30, 0.66), "mid": (0.55, 0.86), "fav": (0.80, 0.96), "cell": (0.90, 0.96)}

def run(strat, rows):
    tmin, lead_thr, z_thr, ml_thr, band = strat
    lo, hi = BANDS[band]
    fills = []
    for d in rows:
        L, V, P = d["leads"], d["vols"], d["prices"]
        pk = 0.0
        for m in TIMING[tmin]:
            l = L.get(m)
            if l is None: continue
            pk = max(pk, abs(l))
            # update peak across earlier minutes too
            for mm in range(0, m+1):
                if L.get(mm) is not None: pk = max(pk, abs(L[mm]))
            if abs(l) < lead_thr: continue
            v = V.get(m)
            if z_thr > 0 and (not v or abs(l)/v < z_thr): continue
            if ml_thr > 0 and pk < ml_thr: continue
            p = P.get(m)
            if p is None: continue
            B = round(min(p+0.01, 0.97), 2)
            if not (lo <= B < hi): continue
            side_up = l >= 0
            won = (side_up == d["up_win"])
            sh = 20 if (0.90 <= B < 0.95) else 5
            fills.append((B, won, sh))
            break
    if not fills: return None
    n = len(fills); w = sum(1 for f in fills if f[1])
    pnl = sum(((1-b) if won else -b)*s for b, won, s in fills)
    return {"n": n, "win": w/n, "ev": pnl/n, "pnl": pnl, "cov": n/len(rows)}

# build grid
grid = list(itertools.product(
    ["early", "mid", "late", "any"],
    [5, 8, 12, 15],
    [0, 2.0, 2.5, 3.0],
    [0, 12, 15, 20],
    ["any", "cheap", "mid", "fav", "cell"]))
print(f"\nsweeping {len(grid)} strategies (train n={len(TRAIN)}, test n={len(TEST)})...\n")

results = []
for s in grid:
    rtr = run(s, TRAIN); rte = run(s, TEST)
    if not rtr or not rte: continue
    if rtr["n"] < 15 or rte["n"] < 10: continue  # need sample both halves
    results.append((s, rtr, rte))

def show(title, key, rev=True):
    print(f"\n=== {title} ===")
    print(f"  {'timing/lead/z/ml/band':32s} {'TRAIN n/win/ev':22s} {'TEST n/win/ev':22s} gap")
    for s, tr, te in sorted(results, key=lambda x: key(x), reverse=rev)[:12]:
        tag = f"{s[0]}/{s[1]}/{s[2]}/{s[3]}/{s[4]}"
        gap = tr["win"] - te["win"]
        print(f"  {tag:32s} {tr['n']:3d}/{tr['win']*100:3.0f}%/{tr['ev']:+5.2f}     "
              f"{te['n']:3d}/{te['win']*100:3.0f}%/{te['ev']:+5.2f}     {gap*100:+4.0f}pp")

# rank by TEST win% (OOS), require decent coverage and small train-test gap
robust = [(s, tr, te) for s, tr, te in results if abs(tr["win"]-te["win"]) <= 0.08]
show("TOP by TEST win% (all)", lambda x: x[2]["win"])
print(f"\n--- OOS-ROBUST subset (|train-test win gap|<=8pp): {len(robust)} configs ---")
_save = results; results = robust
show("TOP by TEST win% (robust)", lambda x: x[2]["win"])
show("TOP by TEST EV/fill (robust, fill-optimistic)", lambda x: x[2]["ev"])
# best win% with meaningful frequency
freq = [(s, tr, te) for s, tr, te in robust if te["cov"] >= 0.25]
results = freq
show(f"TOP win% with coverage>=25% ({len(freq)} configs)", lambda x: x[2]["win"])
results = _save
print("\nNOTE: assume-fill -> EV optimistic (esp. cheap bands fill only on reversal = adverse). "
      "Rank on TEST win% + small gap + coverage. Real-money probe still required before deploy.")
