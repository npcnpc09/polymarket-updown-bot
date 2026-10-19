---
name: btc-vol-regime-gate-has-signal
description: "BTC realized-vol regime gate HAS real signal, RE-CONFIRMED on 197 live fills after an n=12 false 'kill' (2026-06-10): vol>=6.5 bucket −$39.55/68% vs vol<6.5 +$6.50/79%, holds in both time-halves; the morning the gate was removed, eth vol>=9 went 46% win / −$33.30 in one afternoon. VOL_CAP=6.5 restored in early_taker_probe.py. Gate reduces bleed to ~breakeven-slightly-positive, not a big edge."
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

2026-06-10, user idea: detect BTC regime, pause the strategy when unfavorable, resume when favorable. Tested BEFORE building (regime_gate_test.py) on 163 real settled trades (early_taker + early_maker, each recorded btc_vol = BTC 1m-return realized vol at entry):
- low vol (<5.6): n=54, win **72%**, net EV **−0.008/sh** (≈breakeven)
- mid vol (5.6-6.6): n=54, win 69%, EV −0.063
- high vol (>6.6): n=55, win **64%**, EV **−0.081/sh**

MONOTONIC gradient (72→69→64 win, −0.008→−0.081 EV) — more convincing than a single bucket. So btc_vol IS a usable regime indicator, UNLIKE directional macro-trend ([[losses-are-reversals-not-direction-errors]] showed 30m/60m trend alignment = no gradient) — because trend direction is priced into the favorite odds, but VOL = reversal intensity is NOT fully priced (high-vol favorites overpriced → −EV; low-vol leads persist).

HONEST LIMITS: even low-vol is only ~breakeven (−0.008), NOT +EV — the gate REDUCES the high-vol bleed, doesn't manufacture edge. n=54/bucket (smallish), thresholds in-sample, sample mostly from the chop era. So it's risk-reduction, not an edge.

IMPLEMENTATION (clean, no separate supervisor): early_taker already records btc_vol per entry; add VOL_CAP — skip entry when btc_vol >= cap (high vol auto-pauses, recovers when vol falls = the user's adaptive gate). Candidate VOL_CAP=6.5 (skip worst tercile, keep volume) or 5.6 (low-vol-only, ~breakeven but sparse). NOT yet deployed (awaiting user). Validate forward — like all in-sample filters, could be regime-luck ([[out-of-sample-catches-overfit]], [[backtests-untrustworthy-even-realistic-crossval]]).
