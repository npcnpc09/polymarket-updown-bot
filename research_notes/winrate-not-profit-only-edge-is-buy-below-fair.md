---
name: winrate-not-profit-only-edge-is-buy-below-fair
description: "PROFIT re-ranking (price model on 600 windows) proved win-rate evolution optimized the wrong thing — at fair prices ALL variants ≈0/negative (market calibrated); the ONLY remaining edge is buying the favorite BELOW fair (execution/maker), quantified ~+2.4pp ROI per 2c, need ≥4c, eebde does +8c. Historical backtest EXHAUSTED — only live maker probe can answer it."
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

2026-06-09: User pushed "我们的变体只研究了成功率,没有研究如何提高收益多赚钱" — and it cracked the whole effort open.

I rebuilt the evolution to optimize PROFIT (EV) instead of capital-weighted win rate, using a real-data-grounded price(lead) model (scripts/evolve_profit.py, 600 cached windows data/lead_paths.json, calibrated from real_taker_backtest: lead5→0.72, 8→0.79, 11→0.87, 20→0.91). Result: **EVERY variant ≈0-to-negative at fair prices.** winRateOpt (the gen-3 win-rate champion, heavy pyramid [1,10,25]) = only +1.2% and fold-unstable; everything else −4% to −13%. The gen-1→3 win-rate evolution (converged to 92% capital-weighted) was optimizing a metric **orthogonal to profit** — it piles money on winners, but winners are expensive (price ≈ win prob). CONFIRMS the deep prior I kept saying but didn't believe: market is calibrated, favorite priced-in, certainty priced-in. See [[er-and-bband-filters-fail-oos]], [[eebde-is-spread-maker-not-directional]], [[maker-price-band-sweet-spot]].

**The one number that matters** (discount sweep — EV if we buy D cents below fair): each 2c cheaper ≈ **+2.4pp ROI**. winRateOpt: D=0→+1.2%, 4c→+5.9%, 8c→+11.0%. eebde's whole alpha = his +8c (paid 0.74 for 0.82-winners). To be healthily +EV we need to buy **≥4c below fair**.

**CAVEAT (don't over-read):** the price model IS ≈"market efficient" by construction (it's the avg fill price), so this isn't proof of no-edge — it's proof that **paying the average price = breakeven**. The open question it can't settle: can we systematically pay BELOW average? Historical backtest has NO order-book history → it is now EXHAUSTED on this question. Stop running more win-rate gens; they answer a settled/irrelevant question.

**Only arbiter left = live maker probe** (scripts/early_maker_live.py, --place tiny post_only on lead side): does a below-fair limit actually FILL, at what ratio, and is the post-fill win rate high enough that fill-price < fair by ≥4c nets +EV. This is the entire ballgame now. Aligns with [[maker-not-real-tested]] (maker real-money fills NEVER tested; honest position OPEN). Per [[dont-fund-experiments-with-working-strategy]] and user discipline ("dry验证成功之后才注资"): the probe is tiny real orders to MEASURE fill ratio, not a funded strategy — present measurement results before scaling.
