"""bt_sol15m_regime_fit.py — do SOL maker & 15m maker losses CLUSTER in an identifiable ex-ante regime
(so we could gate to the 'suitable' regime), or are they STRUCTURAL (lose across regimes)? Split each by
own vol30 (logged at entry) and by entry-price band. Small samples -> illustrative."""
import json, re, statistics as st
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def load(f):
    out = []
    for o in (json.loads(l) for l in open(ROOT+"/"+f, encoding="utf-8") if l.strip()):
        if o.get("filled") is True and o.get("won") is not None and o.get("pnl") is not None:
            out.append({"won": bool(o["won"]), "pnl": float(o["pnl"]), "B": o.get("B"), "vol": o.get("vol30"), "z": o.get("zscore"), "maxlead": o.get("max_lead")})
    return out
for f, name in (("data/multi_window_engine_sol_live.jsonl", "SOL maker"), ("data/multi_window_engine_15m_live.jsonl", "15m maker")):
    d = load(f)
    n = len(d); w = sum(1 for x in d if x["won"]); pnl = sum(x["pnl"] for x in d)
    print(f"\n=== {name}: {n} fills, win% {w/n*100:.0f}, PnL ${pnl:+.2f} ===")
    # by own vol30
    print("  by own vol30:")
    for lo, hi, lab in ((0, 5, "vol<5(calm)"), (5, 8, "5-8"), (8, 99, "vol>=8(hi)")):
        s = [x for x in d if x["vol"] is not None and lo <= x["vol"] < hi]
        if s:
            sw = sum(1 for x in s if x["won"]); sp = sum(x["pnl"] for x in s)
            print(f"    {lab:12s} n={len(s):3d} win%={sw/len(s)*100:5.0f} PnL=${sp:+7.2f}")
    # by entry band
    print("  by entry-price band:")
    for lo, hi, lab in ((0, 0.90, "<0.90"), (0.90, 0.96, "0.90-0.95cell")):
        s = [x for x in d if x["B"] is not None and lo <= x["B"] < hi]
        if s:
            sw = sum(1 for x in s if x["won"]); sp = sum(x["pnl"] for x in s)
            print(f"    {lab:14s} n={len(s):3d} win%={sw/len(s)*100:5.0f} PnL=${sp:+7.2f}")
print("\nREAD: if losses CLUSTER in one vol/band bucket (and another bucket is clearly +EV) -> a regime gate")
print("could help (trade only the +EV bucket). If losses SPREAD across buckets -> structural, gate won't fix.")
