---
name: twosided-maker-adverse-selection-negev
description: "REGIME-DEPENDENT (n=18, 2026-06-09; corrected from 'firm −EV' after user pushback 'does it always lose?'). Two-sided maker = MIRROR of lead-follower: +EV in sustained CHOP (both sides fill, cost~1-2D<$1), −EV in TREND (fills only the LOSING side = adverse). Net = chop% × (+) + trend% × (−). mid-6c breakeven ≈75% chop windows; our mixed/trendy sample had 56-67% chop → net −EV. NOT 'always losing'. Lead-follower + two-sided are mirrors → combining ≈ breakeven. Only possible +EV path = run two-sided ONLY when chop predicted (untested)."
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

2026-06-09, user asked: in chop-heavy markets can we bet both sides like ce25? Built passive_twosided.py (zero money, real order book; snapshot mid_Up/mid_Down ~45s, rest hypothetical bids mid-0/2/4/6c each side, track each token's real min-ask = would-fill, settle by binance winner) + analyze_twosided.py -> data/twosided.jsonl.

First table (n=8 windows, SMALL but mechanism crisp):
- both-fill% drops with discount: mid-0c 88% / mid-2c 62% / mid-4c 50% / mid-6c 50%
- **both-fill-window EV = POSITIVE, grows with D**: +0.00 / +0.04 / +0.08 / +0.12 (≈2D — chop windows where both fill DO profit, exactly as theory: cost≈1-2D<$1, one side pays $1)
- **one-fill-window EV = strongly NEGATIVE**: −0.31 to −0.39 (TREND windows fill only the side price left = the LOSING side = adverse selection)
- **NET EV/window = negative at ALL tiers**: −0.038 / −0.122 / −0.149 / −0.119. Adverse-selection loss from trend windows swamps the chop profit. Deeper D = more chop profit BUT more adverse one-fill windows (12%→50%); the tax wins.

VERDICT: the user's intuition is HALF right — chop two-sided fills ARE +EV (mechanism real, data-confirmed) — but the trend-window adverse selection kills net EV. Pure two-sided neutral maker = −EV for us = the classic small-MM adverse-selection death ([[fast-maker-strategy-validated]], [[taker-only-execution]]). CAVEAT: passive=front-of-queue=fill UPPER bound, so real EV likely WORSE; n=8 small (observer keeps collecting). Why ce25 profits anyway: he is NOT a pure neutral two-sided maker — value-weight + continuous averaging reloads the STRENGTHENING (winning) side, converting the adverse selection into net-long-favorite ([[eebde-is-spread-maker-not-directional]], [[ce25-selection-decoded]]); needs his scale + averaging machinery, and per-trade edge is still thin +2.7% ([[profit-map-barbell-and-blind-benchmark]]). So: don't deploy a pure two-sided maker; it doesn't solve the chop-regime problem (it gets adversely selected in trends instead).
