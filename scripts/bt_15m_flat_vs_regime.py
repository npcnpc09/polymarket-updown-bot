"""bt_15m_flat_vs_regime.py — DIRECT head-to-head on the cached 578 PM-priced 15m windows:
FLAT z2.5 vs REGIME-SWITCH, on a PROFIT basis (not just win%). Same windows, same maker fill model
(assume-fill, B=price+0.01, cell 20sh @0.90-0.95). Time-split train/test. Answers: did the backtest
ever actually show regime-switch BEATS flat z2.5 on $ (it was only ever ranked by win% before)?"""
import json
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
data = json.load(open(ROOT+"/data/bt15m_cache.json"))
for d in data:
    d["leads"] = {int(k): v for k, v in d["leads"].items()}
    d["vols"] = {int(k): v for k, v in d["vols"].items()}
    d["prices"] = {int(k): v for k, v in d["prices"].items()}
data = sorted(data, key=lambda d: d["start"])
cut = int(len(data)*0.6); TRAIN, TEST = data[:cut], data[cut:]

def classify(d):
    L = d["leads"]
    seq = [L[m] for m in range(1, 10) if L.get(m) is not None]
    flips = sum(1 for i in range(1, len(seq)) if (seq[i] >= 0) != (seq[i-1] >= 0)) if len(seq) > 1 else 0
    pk = max((abs(x) for x in seq), default=0.0)
    l9 = L.get(9)
    persist = (abs(l9)/pk) if (l9 is not None and pk > 0) else 0.0
    return "trend" if (flips <= 1 and persist >= 0.7) else "chop"

def entry(d, mode):
    L, V, P = d["leads"], d["vols"], d["prices"]
    reg = classify(d)
    for m in range(9, 15):
        l = L.get(m)
        if l is None or abs(l) < 8: continue
        v = V.get(m); z = abs(l)/v if v else 0
        pk = max((abs(L[k]) for k in range(0, m+1) if L.get(k) is not None), default=0.0)
        if mode == "flat":
            if z < 2.5: continue
        else:  # regime-switch
            if reg == "chop" and not (z >= 2.0 and pk >= 20): continue
            # trend: loose (lead>=8 enough)
        p = P.get(m)
        if p is None: continue
        B = round(min(p+0.01, 0.97), 2)
        if not (0.30 <= B <= 0.95): continue
        won = ((l >= 0) == d["up_win"]); sh = 20 if (0.90 <= B < 0.95) else 5
        return (B, won, sh, reg)
    return None

def agg(rows, mode):
    fills = [e for e in (entry(d, mode) for d in rows) if e]
    if not fills: return None
    n = len(fills); w = sum(1 for f in fills if f[1])
    pnl = sum(((1-b) if won else -b)*s for b, won, s, _ in fills)
    cost = sum(b*s for b, won, s, _ in fills)
    return {"n": n, "win": w/n*100, "pnl": pnl, "ev": pnl/n, "cov": n/len(rows)*100, "margin": pnl/cost*100 if cost else 0}

def show(label, rows):
    print(f"\n=== {label} (n_windows={len(rows)}) ===")
    for mode in ("flat", "regime"):
        r = agg(rows, mode)
        nm = "FLAT z2.5    " if mode == "flat" else "REGIME-SWITCH"
        print(f"  {nm}  traded={r['n']:3d} ({r['cov']:2.0f}%)  win%={r['win']:4.1f}  "
              f"PnL=${r['pnl']:+7.2f}  EV/fill=${r['ev']:+.3f}  margin={r['margin']:+.1f}%")

show("ALL 578", data)
show("TRAIN (early 60%)", TRAIN)
show("TEST (held-out 40%)", TEST)

# what the regime-switch SKIPS that flat would trade, and vice-versa
print("\n=== where they differ (ALL) ===")
both = reg_only = flat_only = 0
ro_pnl = fo_pnl = 0.0
for d in data:
    f = entry(d, "flat"); r = entry(d, "regime")
    if f and r: both += 1
    elif r and not f: reg_only += 1; ro_pnl += ((1-r[0]) if r[1] else -r[0])*r[2]
    elif f and not r: flat_only += 1; fo_pnl += ((1-f[0]) if f[1] else -f[0])*f[2]
print(f"  both trade={both} | regime-only (flat skips)={reg_only} PnL=${ro_pnl:+.2f} | "
      f"flat-only (regime skips chop)={flat_only} PnL=${fo_pnl:+.2f}")
print("\nNOTE: assume-fill maker model -> EV optimistic; RELATIVE flat-vs-regime is the read. The key Q: "
      "does regime-switch's $ beat flat's $? (win% was the only metric the earlier regime backtests used.)")
