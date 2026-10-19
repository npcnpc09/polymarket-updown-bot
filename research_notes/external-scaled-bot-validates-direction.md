---
name: external-scaled-bot-validates-direction
description: "An external Claude-built quant bot ($232k/73d, 47% win, Kelly, 'price-lag early entry') = EXACTLY our ce25/early-taker strategy at scale. Validates the direction; the gap to us is capital+diversification+Kelly, NOT signal. But unverified, one-regime, Kelly cuts both ways."
metadata: 
  node_type: memory
  type: reference
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

**User showed (2026-06-08) an external Claude-built Polymarket quant bot:** 73 days, +$232k profit, ~$3180/day, ~7.5 trades/hr, 13,070 predictions, **47% win rate**, $248.9k deposited, ROI +93%. Strategy (their words): find markets where price hasn't caught up to real volatility, position BEFORE the odds fully adjust, repeat the same small edge, scale with Kelly, compound. Standout trades like $6757→$24330 (= buying a side at ~0.28 and winning = cheap-side multiple).

**This is EXACTLY our decoded strategy at scale** — [[ce25-selection-decoded]] + [[early-taker-probe-live]]. The "price-lag / enter before odds adjust" = the early-taker pricing-lag edge; "repeat the same small edge + Kelly + compound" = diversified value-weighting. The **47% win rate is the fingerprint = ce25's exact profile** (we measured ce25 at 46% win, profitable via cheap-side × odds, NOT high win rate). The standout-trade shape (buy ~0.28, win ~3.6x) IS the cheap-side harvest. So our whole-session decode is independently validated by a live scaled instance.

**The gap between us and this bot = SCALE, not signal.** We HAVE the signal (z-score / lead-persistence / pricing-lag). They have what we lack: capital ($248k vs our $84→$140), diversification (13,070 trades vs our ~11 live), and Kelly sizing — which our own mc_scale.py concluded is the REQUIREMENT (value-weight/Kelly is 0-EV and drawdown-amplifying WITHOUT diversification; needs N=hundreds-thousands of windows + capital). They have that apparatus; we don't.

**DISCIPLINE caveats (per [[no-conclusions-without-longrun-and-they-expire]], [[true-pnl-baseline]]):** (1) numbers UNVERIFIED; (2) 73 days = ONE regime — could be a favorable-regime Kelly compounding run that hasn't hit its drawdown (cf. our own $59→$113→gave-back); (3) Kelly is double-edged — exponential up in good regime, exponential drawdown in bad; 73d likely hasn't seen a real bad regime; (4) standout-trade framing = standard packaging of impressive results; 47% win = MORE losers than winners, the full ledger isn't shown.

**Correct sequence for us (do NOT skip to scale):** first confirm early-taker's edge is DURABLE (survives a choppy/high-vol OOS regime) at tiny scale → THEN scale with capital + diversification + Kelly → AND rotate the compromised wallet ([[live-trade-permission-mechanism]] wallet) before scaling. Confirming-durable-first is the whole point of the current live probe; the $232k script is what it could look like AFTER durability is proven, not before. Scaling Kelly before proving durability = the exact "good-regime compounding / bad-regime blowup" trap.
