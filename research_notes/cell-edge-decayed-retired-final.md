---
name: cell-edge-decayed-retired-final
description: "Cell FINALLY stopped 2026-07-13 at $322.84 (broke user's $325 stop). Root cause = EDGE DECAY by competition (per-trade +$0.41 June -> -$0.55 now), NOT regime. Re-entry needs a NEW edge or fixed execution (shorter confirm for queue priority), not waiting."
metadata: 
  node_type: memory
  type: project
  originSessionId: 916a529c-1bc3-4803-a10c-1e88d28c8e6d
---

2026-07-13: cell stopped for good (user OK) at wallet $322.84 all-cash — broke the user's $325 hard stop. floor-8 restart (07-12) bled -$24.65 in ~1 day. All --place + killswitch stopped. Running: wallet_logger + 3 alt_exec DRY + taker/copy/weather = 7 python / 0 --place.

**WHY cell died — diagnosed thoroughly (user pushed each hypothesis, all tested):**
1. Not oracle mismatch: TRUE Chainlink reverses LESS than binance (5.9% vs 7.1%), more favorable (+$318 vs +$153 on 2117 windows). [[reversal-harvest-oracle-gap-refuted]]
2. Not regime: reversal rate HEALTHY 5-6% throughout the bleed (bad-regime stops were 07-08/09; THIS is different — good market, still loses).
3. Not the lead floor: [[leadfloor-refuted-true-settle]] (removing it didn't help; new 8-14 band bled slightly worse live).
4. Reversal not harvestable: pullback-triggered underdog = -62.5% (underdog reprices to 0.34 by the time pullback detectable; the +130% mirror on our fills is unreachable — same wall as two-sided-arb).
5. **THE ROOT: EDGE DECAY.** Live cell weekly per-trade: W24 +$0.41, W26 +$0.34, W27 +$0.08, W28 -$0.12, W29 -$0.55. Win rate stayed ~90% throughout — cell never won on win-rate, it won on small-wins-outrunning-big-reversal-losses. That ratio flipped as the thin edge (favorite-longshot mispricing + cheap maker entry) got competed away. June profit (+$270 W24-27, 900 trades) was REAL, not variance; markets adapted.

**User's best hypothesis (plausible, unprovable from data)**: our 15s CONFIRM wait + intensified competition = we rest bids LATE -> worse queue position -> faster bots take the good noise-pullback fills (89% win), we're left adversely selected into reversals. DRY can't prove it (its maker-fill model is queue-BLIND — assumes fill if ask touches our bid), which is exactly why DRY stayed +/stable while live decayed. Entry offset DID drift later (0.35->0.42) recently. [[entry-timing-edge-curve]]: buy-below-fair edge is biggest EARLIEST (z2.5 min1 +18.4pp -> min3 +6.9pp), so waiting forfeits the fat edge.

**Cell lifetime**: peak $443.36 (06-29) -> $322.84 (07-13) = -$120. Of the early drop, ~-$44 was non-cell (stacking bug, taker) since fixed. Cell itself: strong June, decayed to -EV by mid-July.

**IF ever revisited**: (a) needs a genuinely NEW edge, OR (b) test drastically SHORTER confirm (enter early for queue priority) — but that's real-money experimentation on a decayed strategy; low priority. Do NOT restart expecting regime recovery to help — the edge is competed away, not regime-suppressed. Pivot: new-strategy research (leaderboard scan for current-regime winners; weather model).
