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
        rows.append((B, ((l >= 0) == w["up_win"]))); break
print("late z>=2.5 entries:", len(rows))
def rep(lo, hi, lab):
    s = [(B, won) for B, won in rows if lo <= B < hi]
    if not s: print(f"  {lab}: n=0"); return
    n = len(s); wn = sum(1 for B, won in s if won)
    ev = sum(((1-B) if won else -B) for B, won in s)/n*5
    ab = sum(B for B, won in s)/n
    print(f"  {lab:16s} n={n:3d} win%={wn/n*100:5.1f} avgB={ab:.3f} EV/5sh={ev:+.3f} breakeven_win={ab*100:.0f}%")
print("=== by price band (real PM settlement, assume-fill) ===")
rep(0.30, 0.85, "<0.85")
rep(0.85, 0.90, "0.85-0.90")
rep(0.90, 0.96, "0.90-0.95 cell")
print()
rep(0.30, 0.90, "ALL <0.90")
rep(0.90, 0.96, "cell >=0.90")
print("\nNOTE: assume-fill -> cheap-band win% is INFLATED (binance/reconstruction longshot bias + adverse-fill")
print("blindness). Live probe showed cheap-band 15m = 67% (real maker fills adverse). Read the RELATIVE band")
print("ordering + remember the backtest can't see the cheap-fill adverse selection that live revealed.")
