---
name: no-filter-without-independent-backtest
description: "FEEDBACK (user, 2026-06-11): NO new filter/strategy goes live without an INDEPENDENT backtest first — analysis of our own live fills is in-sample mining, even when it looks cross-validated (both engines, 4/4 days). The flip60 gate proved the point: deployed off live-fill analysis, independent backtest immediately refuted it."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 8f4a16b0-b790-40ee-819d-682c2f47380e
---

**What happened:** I found flip60>0.51 separated bleed inside the vol gate on our 260 live fills — looked strong (both engines same direction, 4/4 days consistent) — and deployed it as skip+track without an independent backtest. User stopped me: "我们还没有回测就不要加任何filter和策略". The independent backtest (60k all-trader real fills, separate dataset) then REFUTED it: choppy bucket edge +6.7% (solidly positive, nowhere near our in-sample −EV), threshold grid non-monotonic (gap +0.5% at 0.51, INVERTS to −1.8% at 0.53), per-day sign flip (06-07 choppy BETTER than calm). The seductive 4/4-day consistency was tiny cells (n=3-21/day).

**Why:** analysis of one's own live fills is in-sample mining no matter how it's sliced — cross-engine/cross-day consistency within the same small dataset is not independence. [[out-of-sample-catches-overfit]] applies to live data too, not just backtests.

**How to apply:**
1. Pipeline for ANY new gate/filter/strategy change: (a) hypothesis from live-fill analysis → (b) INDEPENDENT backtest (different dataset: all-trader fills, binance reconstruction, different period) → (c) only if confirmed, deploy — skip+track form preferred → (d) forward validation.
2. "skip+track is conservative" is NOT an exemption — it still removes real trades and was the argument I used to skip step (b).
3. This complements [[btc-vol-regime-gate-has-signal]] (vol gate DID pass: 197-fill + both-time-halves + same-day causal evidence) and the climax skip (DRY+live+threshold-grid backtest before deploy). The bar those met is the bar.
