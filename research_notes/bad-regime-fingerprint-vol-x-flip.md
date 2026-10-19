---
name: bad-regime-fingerprint-vol-x-flip
description: "2026-06-11 regime analysis on 260 live fills: the bad-regime fingerprint = move SIZE (vol) x direction PERSISTENCE (flip rate) — two orthogonal axes. flip60>0.51 separates the residual bleed WITHIN the deployed vol<6.5 gate (taker calm 89.5%/+$20.75 vs choppy 70.8%/-$9.15, consistent both engines, 4/4 days). Deployed as skip+track on taker only. Losses do NOT cluster in time."
metadata: 
  node_type: memory
  type: project
  originSessionId: 8f4a16b0-b790-40ee-819d-682c2f47380e
---

**Question (user, 2026-06-11): can the bad-walk regimes be identified from market features?** Analysis on all 260 live fills (154 taker + 106 z-maker) joined with trailing-60m btc 1m-kline features computed at entry time (real-time computable = deployable).

**The fingerprint has TWO orthogonal axes:**
1. **Move size = vol** (deployed since 06-10): top vol60 quartile (>9.45 bps/min) = 62.5% win, −$48 = worst bucket. Mid-vol is muddy/non-monotonic; the gate earns its keep at the extreme.
2. **Direction persistence = flip rate** (NEW): btc 60m sign-alternation rate of 1m returns. Lowest quartile (<0.47) is the ONLY positive quartile overall (+$18.80); within the vol<6.5 universe flip60>0.51 still separates: taker calm-flip 89.5% win +$20.75/38 vs high-flip 70.8% −$9.15/24, **consistent across BOTH engines and 4/4 meaningful days** (06-07/09/10 calm≫choppy, 06-08 both green). Mechanism: our entry IS a breakout-follow; in low-persistence regimes the 8bps lead is a mean-reverting oscillation, the favorite is priced as if it holds, and we buy the top of the swing. Vol can be LOW while flip is HIGH (quiet sawtooth) — that's the bleed the vol gate can't see.
3. **ER (efficiency ratio) re-tested and re-failed** (non-monotonic, Q4 cleanest-trend hours actually negative) — consistent with [[er-and-bband-filters-fail-oos]]; don't revisit.
4. **Losses do NOT cluster in time**: P(loss | prev loss <1h) = 21.6% vs P(loss | prev win) = 21.2%. "Stop after N losses" / loss-streak circuit breakers carry no information at the 1h scale; regime must be read from FEATURES, not from recent outcomes. (z-maker alone showed mild clustering 33% vs 10% on n=12 — too small.)

**REFUTED 2026-06-11 ~01:00 — flip gate did NOT survive independent backtest.** Deployed at 00:42 off the live-fill analysis, user invoked the no-backtest-no-filter rule, reverted, then tested on 60k all-trader real fills ([[no-filter-without-independent-backtest]]): choppy bucket edge +6.7% (POSITIVE — nothing like our in-sample −EV), threshold grid non-monotonic (gap +0.5% at 0.51, inverts −1.8% at 0.53), per-day SIGN FLIP (06-07 choppy beat calm +7.9% vs +4.4%). The in-sample 4/4-day consistency was tiny cells. FLIP_CAP now 1.01 (disabled); flip60 still computed & logged on every taker row (free instrumentation — revisit ONLY with a fresh independent test if the logged data ever shows a stable pattern). The vol axis stands (it passed real validation); the flip axis is dead pending new evidence. The losses-don't-cluster finding (21.6% vs 21.2%) is descriptive and stands.

**VOL-COOLDOWN (hysteresis) also REFUTED 2026-06-11 pm:** user proposed "after a vol pulse, wait for stability before re-entering" (motivated by 3 afternoon losses in pulse gaps). Backtest on 7,572 independent gate-passing fills: **0-10min after a pulse is the BEST bucket (+15.6% edge)**, >60min-since-pulse the worst (+8.1%); our own 136 fills agree (0-10min +$9.60, only negative bucket sandwiched mid-range = noise). Mechanism: pulse creates real displacement, fast vol normalization = market accepted the new level → cleanest follow-through. Do NOT re-propose cooldown/hysteresis on the vol gate; the instant-vol check at entry is already the validated optimum. (Second filter idea killed by the backtest rule in one day — flip60 morning, cooldown evening.)
