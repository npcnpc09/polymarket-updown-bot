---
name: no-conclusions-without-longrun-and-they-expire
description: "Core working principle (user, 2026-06-06) — do NOT state conclusions without long-term repeated trials/experiments; and ANY conclusion has an expiry, it stops being valid after a while (regime change). Hold findings as provisional, time-stamped, and regime-bound."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

User's explicit instruction (2026-06-06), to apply to ALL of this trading work and analysis:

1. **No conclusions without long-term, repeated trials.** A single backtest, a small live sample, or a paper probe is NOT enough to conclude anything. Do not hand the user "X works" / "X is dead" / "we can't do Y" unless it's backed by repeated experiments over time. Until then the position is OPEN / provisional, and say so.

2. **Every conclusion has an expiry.** Even a well-supported finding stops being valid after a while — the market regime changes and the edge/relationship decays or flips. So: time-stamp findings, treat them as valid only for the regime they were measured in, and re-validate before relying on an old conclusion. "It held last week" ≠ "it holds now."

**Why:** this session repeatedly proved it — signals looked great in-sample then failed OOS (persist, macro, B-band, ER, $300 threshold); the same signal printed +$ then bled -$ as the regime flipped (counter-trend bounce); "5m>15m" reversed; cushion/15m worked one slice and not another; I twice handed premature conclusions ("stop the bot" off redemption-lag snapshots; "maker -EV" off paper) that the user correctly rejected. The market is calibrated and non-stationary — nothing here is a permanent truth.

**How to apply:**
- Phrase findings as provisional + dated + regime-bound: "in this ~Nh down-regime slice, X looked like Y (n=…); needs repeated/forward validation; may not hold next regime."
- Before acting on any prior memory finding, check it still holds NOW (re-run, don't trust the old number).
- Resist the urge to "wrap up" with a clean verdict — the honest state is usually "provisional, watching."
- Treat even the dual-validated ones (e.g. lead>=5 filter, cushion) as current-regime-valid, not permanent.
