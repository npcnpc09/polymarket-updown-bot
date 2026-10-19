"""bt_15m_gate.py — backtest candidate 15m gates on cached real-PM 15m windows (late z>=2.5 entries).
Tests the low-vol-z-inflation hypothesis: do LOW-vol / LOW-abs-lead entries (z inflated by tiny vol) win
less? Split by vol30 and by |lead| at entry. win% + EV (real PM settlement; win% is signal-quality, less
fill-dependent than the cheap-band which is an assume-fill trap)."""
import json, statistics as st
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
d = json.load(open(ROOT+"/data/bt15m_cache.json"))
for w in d:
    w["leads"] = {int(k): v for k, v in w["leads"].items()}
    w["vols"] = {int(k): v for k, v in w["vols"].items()}
    w["prices"] = {int(k): v for k, v in w["prices"].items()}
rows = []
for w in d:
    L, V, P = w["leads"], w["vols"], w["prices"]
    for m in range(9, 15):
        l = L.get(m)
        if l is None or abs(l) < 8: continue
        v = V.get(m)
        if not v or abs(l)/v < 2.5: continue
        p = P.get(m)
        if p is None: continue
        B = round(min(p+0.01, 0.97), 2)
        if not (0.30 <= B <= 0.95): continue
        rows.append({"won": ((l >= 0) == w["up_win"]), "B": B, "vol": v, "lead": abs(l), "z": abs(l)/v}); break
n = len(rows)
print(f"late z>=2.5 entries: {n} | base win% {sum(1 for r in rows if r['won'])/n*100:.1f}")
def rep(pred, lab):
    s = [r for r in rows if pred(r)]
    if not s: print(f"  {lab}: n=0"); return
    wn = sum(1 for r in s if r["won"]); ab = sum(r["B"] for r in s)/len(s)
    ev = sum(((1-r["B"]) if r["won"] else -r["B"]) for r in s)/len(s)*5
    print(f"  {lab:18s} n={len(s):3d} win%={wn/len(s)*100:5.1f} avgB={ab:.3f} EV/5sh={ev:+.3f} breakeven={ab*100:.0f}%")
print("\n=== by own vol30 (low-vol z-inflation test) ===")
rep(lambda r: r["vol"] < 5, "vol<5 (calm)")
rep(lambda r: 5 <= r["vol"] < 8, "vol 5-8")
rep(lambda r: r["vol"] >= 8, "vol>=8")
print("\n=== by |lead| at entry (abs-lead floor test) ===")
rep(lambda r: r["lead"] < 12, "lead 8-12 (weak)")
rep(lambda r: 12 <= r["lead"] < 20, "lead 12-20")
rep(lambda r: r["lead"] >= 20, "lead>=20")
print("\n=== candidate gates: KEEP set EV vs base ===")
rep(lambda r: True, "ALL (no gate)")
rep(lambda r: r["vol"] >= 5, "GATE vol>=5")
rep(lambda r: r["lead"] >= 12, "GATE lead>=12")
rep(lambda r: r["B"] >= 0.90, "GATE B>=0.90 (cell)")
rep(lambda r: r["vol"] >= 5 and r["lead"] >= 12, "GATE vol>=5 & lead>=12")
print("\nNOTE: win% by vol/lead is signal-quality (real settlement, fill-independent). EV uses assume-fill")
print("(cheap-band inflated). Look for a gate where the KEPT set has higher win% AND the dropped set was -EV.")
