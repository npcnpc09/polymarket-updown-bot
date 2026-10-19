---
name: true-pnl-baseline
description: "Correct PnL baselines — TOTAL CONTRIBUTED CAPITAL = $255 ($200 original + $55 injected 06-08); TRUE BREAK-EVEN = $255 (user-stated 2026-06-11). Round baseline $139.53."
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

The wallet baselines / timeline (user clarified 2026-06-05):

- **Original capital: $200.**
- **When broader strategy work began: ~$97.**
- **When the LATEST strategy (multi-window taker) started: $59.** This IS a valid baseline for the latest strategy — I briefly over-corrected and wrongly dismissed it; $59 is correct for the current strategy arc.
- **Latest strategy peak: $113.**
- **Now (2026-06-05): $90.24.**

So the latest multi-window taker arc = **$59 → $113 (peak, +$54) → $90 (gave back $23)**, netting **+$31 vs its $59 start**, but **−$23 off the $113 peak**, and **−$110 vs original $200**.

Read: the $59→$113 run-up was very likely favorable-regime variance, NOT structural alpha; the $113→$90 bleed is reversion toward breakeven (correlated multi-window tail + the −EV medium-trend chop zone eating it back). The net is drifting from +$54 toward breakeven — consistent with the research verdict "taker on a calibrated market = no alpha, only friction" (see [[er-and-bband-filters-fail-oos]], [[maker-price-band-sweet-spot]], [[taker-only-execution]]).

**How to apply:** report the latest strategy vs $59 (start) AND vs $113 (peak, to show the drawdown) AND vs $200 (original). Don't cherry-pick the +$31 and call it a win — it peaked at +$54 and is reverting. Account for ~5min redemption lag before judging a dip (a dip to $80 recovered to $90 via late redemptions).

**TRUE BREAK-EVEN = $255 (user-stated 2026-06-11): $200 original + $55 injected = total contributions.** "回本" means wallet $255, not $200 and not $139.53. Report progress vs THREE lines: round baseline $139.53 (this run's start), $255 (true break-even), plus the current-run low/peak for trajectory. As of 2026-06-11 ~05:15: wallet $113.70 → −$25.83 vs round start, **−$141.30 vs true break-even** — at the realistic +$2-5/day tiny-scale run-rate, full recovery needs months or a (post-wallet-rotation, post-validation) scale-up; set expectations accordingly.

**CAPITAL INJECTION 2026-06-08: user injected ~$55** (wallet $84.58 → $139.53 same day; confirmed "注资"). This is NEW CAPITAL, not trading profit — do NOT read the wallet rise as PnL. New cash baseline ≈ $139-140 as of 2026-06-08 ~04:50 (before the [[early-taker-probe-live]] real-money run). Going forward, measure trading PnL against the post-injection base, and track cumulative injections separately so the wallet number isn't mistaken for performance. (Original $200 + this $55 etc. are CONTRIBUTIONS; alpha = wallet − contributions.)
