---
name: losses-are-reversals-not-direction-errors
description: "Decomposition of 155 real settled trades (2026-06-09) — our losing trades did NOT pick the wrong direction. Losers had STRONGER entry lead (+5.5) than winners (+3.1); the difference is winners' lead BUILDS (peak +20.7) while losers' peaks at +12.6 then REVERSES. 66% of losses = strong lead (≥8) that reversed before settle (irreducible priced-in tail), 23% weak/marginal entries (reducible by higher threshold), 34% tight-call oracle noise (binance≠Chainlink)."
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

2026-06-09, user asked "why did the losing trades pick the wrong direction?" Ran analyze_losses.py: for every real settled trade (early_taker + early_maker), bought side = lead side; fetched binance 1s lead path; characterized vs bought side. 155 windows (108 won / 47 lost).

**The direction was NOT wrong at entry.** Losers' entry lead (+5.5 @45s) was actually STRONGER than winners' (+3.1). The discriminator is PERSISTENCE, not entry strength: winners' lead BUILDS to peak +20.7 and ends +14.2; losers' lead peaks at only +12.6 then REVERSES to end −6.9. You cannot tell at entry whether a real lead will keep building (win) or reverse (lose).

**Loss decomposition (n=47):**
- **66% = REVERSAL** (lead reached ≥8 then flipped to lose) — the irreducible reversal tail. Not a selection error; the signal was correct at entry, the market reversed. This is exactly why favorites are priced 0.72-0.85 (the ~15-30% reversal rate is priced in). Unfixable by better entry direction.
- **23% = WEAK** (peak lead never reached 8 = marginal/noise entry) — reducible by raising the entry threshold (require the lead to BUILD/confirm stronger), but that also cuts some marginal wins.
- **34% = TIGHT** (|final lead| < 5 bps = near coin-flip at settle) — binance(our signal)≠Chainlink(actual settlement, [[updown-resolution-source-chainlink]]) oracle noise; some "losses" aren't direction errors at all.

MACRO-TREND FILTER TESTED & REFUTED (analyze_macro_trend.py, same 156 windows): does the broader BTC trend (prior 30m/60m return before the window) predict whether the 5m lead persists or reverses? NO. Aligning the 5m bet with BTC's prior-30m trend gave LOWER win rate (66%) than counter (73%, −7pp wrong way); prior-60m = 70/70 (zero); coin's own 30m = 69/70 (zero). The slight counter-30m tilt is NOISE (60m shows nothing — a real effect wouldn't vanish across timeframes; n=71-85). So the larger BTC trend does NOT cut the 66% reversals — the 5m outcome is ~independent of the macro trend (it's public info, already priced into the favorite's odds). Don't re-test macro/HTF trend as a reversal filter.

CONCLUSION: there is no direction-selection alpha to recover — the entry signal is already correct; losses are dominated by unpredictable reversals of genuinely-strong leads (priced-in tail), not by picking the wrong side. Reconfirms selection is priced-in ([[winrate-not-profit-only-edge-is-buy-below-fair]], [[losses-are-reversals... ]] points back to execution/buy-cheap as the only lever). The only entry-side tweak with any merit = a higher build/confirm threshold to trim the 23% weak entries (marginal, OOS-risky — past acceleration/confirm gates failed OOS, [[signal-stop-doubles-roi]] [[er-and-bband-filters-fail-oos]]).
