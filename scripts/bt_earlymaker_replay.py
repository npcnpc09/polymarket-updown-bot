"""bt_earlymaker_replay.py — replay early_maker's strategy on the cached real-PM 15m windows.
early_maker logic: at EARLY checkpoints (~min 2..6), if |lead|>=5, post maker bid ~ price, SKIP if
price>=0.85 (PRICE_CAP), hold to settle. Multiple fills/window (scale-in). win=real PM settlement.
Compare to its REAL live: 88% win / avg entry 0.724 / +$36.80 (49 fills). CAVEAT: assume-fill INFLATES
cheap entries (the fill that actually happens is adverse) — so this is the OPTIMISTIC bound."""
import json, statistics as st
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
d = json.load(open(ROOT+"/data/bt15m_cache.json"))
for w in d:
    w["leads"] = {int(k): v for k, v in w["leads"].items()}
    w["prices"] = {int(k): v for k, v in w["prices"].items()}
LEAD_MIN = 5.0; CAP = 0.85; CHECK = [2, 3, 4, 5, 6]   # early checkpoints (min), 15m early window
fills = []
for w in d:
    L, P = w["leads"], w["prices"]
    for m in CHECK:
        l = L.get(m)
        if l is None or abs(l) < LEAD_MIN: continue
        p = P.get(m)
        if p is None: continue
        side_up = l >= 0
        B = p if side_up else (1-p)   # favorite-side price for the lead direction
        if B >= CAP: continue          # PRICE_CAP skip
        won = (side_up == w["up_win"])
        fills.append((B, won))
n = len(fills)
if n:
    w_ = sum(1 for B, won in fills if won)
    ab = sum(B for B, won in fills)/n
    ev = sum(((1-B) if won else -B) for B, won in fills)/n*5
    pnl = sum(((1-B) if won else -B)*5 for B, won in fills)
    print(f"=== early_maker replay on {len(d)} cached 15m windows (~6d real PM) ===")
    print(f"  fills={n} win%={w_/n*100:.1f} avgEntry={ab:.3f} EV/5sh={ev:+.3f} totalPnL(5sh)=${pnl:+.2f}")
    print(f"  (real live early_maker 15m: 88% win, avg 0.724, +$36.80/49 fills)")
    print("\n  by entry band:")
    for lo, hi, lab in ((0, 0.5, "<0.50"), (0.5, 0.7, "0.50-0.70"), (0.7, 0.85, "0.70-0.85")):
        s = [(B, won) for B, won in fills if lo <= B < hi]
        if s:
            sw = sum(1 for B, won in s if won); sb = sum(B for B, won in s)/len(s)
            sev = sum(((1-B) if won else -B) for B, won in s)/len(s)*5
            print(f"    {lab:10s} n={len(s):3d} win%={sw/len(s)*100:5.1f} avgB={sb:.3f} EV/5sh={sev:+.3f} breakeven={sb*100:.0f}%")
print("\nNOTE: assume-fill = OPTIMISTIC. cheap early bids fill only on pullbacks (adverse) so REAL win% is")
print("LOWER than shown. The 15m regime DRY 'early' track (real fwd) was 71% / -EV. This replay's win% is the")
print("ceiling, not the expectation.")
