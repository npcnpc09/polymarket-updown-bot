---
name: profit-map-barbell-and-blind-benchmark
description: "Real-fill profit map (ce25's actual prices×outcomes) + all-trader BLIND benchmark — his edge is SELECTION not band (~+2.7% overall × volume), blind bands don't replicate it, cheap side (0-0.3) is binance-reconstruction garbage, and very-strong favorites (0.9-1.0) are genuinely OVERPRICED blind (−7.5%, n=15238). Win-rate line AND profit line both converge on the same bottleneck: execution (buy below fair / maker)."
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

2026-06-09, opening the max-PROFIT line (after closing win-rate, [[winrate-max-converged-closed]]).

**profit_cells.py** (ce25's REAL fills: real price+size+outcome, joined to 600-window cache's REAL winners = unbiased): his overall real ROI = **+2.7%** (thin — his $969k = +2.7% × huge volume, NOT a fat per-trade edge). Profit map is a **barbell**: cheap longshots (0.1-0.3) + strong favorites (0.8-0.9) make money; **moderate favorite 0.7-0.8 LOSES −1.9%** (= exactly the band our live early-taker bled, [[cheap-side-profits-favorite-band-loses]] re-confirmed on his real data).

**blind_band_benchmark.py** (77,698 ALL-trader buys, 160 windows, binance winner): tests if each band is +EV blind (replicable) or only for ce25 (selection). Verdict — **his edge is SELECTION, not band**: 0.2-0.3 ce25 +5.9% but blind −28.7%; 0.8-0.9 ce25 +4.8% but blind −4.2%. His per-band win% beats blind by ~3-7pp everywhere. Blind bands are calibrated-to-negative.

**Two hard, reliable takeaways:**
1. **Cheap side (0.0-0.3) is UNRELIABLE** — blind 0.0-0.1 shows +237% ROI/+11pp = the binance-reconstruction artifact ([[binance-reconstruction-inflates-longshots]], near-determined longshots, 1m-kline winner ≠ real settlement). Discard cheap-band blind numbers.
2. **Very-strong favorites 0.9-1.0 are genuinely OVERPRICED blind: −7.5% ROI, −6pp, n=15238** (favorite side = binance reliable). Pay 0.958, win 90%. → **HARD RULE: never buy favorites ≥0.85 (definitely not ≥0.9).** And this is the clean proof that win-rate≠profit: the win-rate champion's heavy late pyramid [1,10,25] loads its biggest add (~25sh) at ~0.9 = straight into the −7.5% overpriced zone → profit-negative by construction.

**GA on REAL settlement = the rigorous close of the "is there a profitable selection RULE" question** (ga_profit_real.py, 277,534 all-trader fills × REAL redeem winners from the 600-window cache, window-level train/test split). Blind-buy-ALL = **−0.2% ROI = breakeven** (market efficient for takers, our most rigorous baseline ever). GA best rule (genome = lead×price×offset ranges): train **+145%** → test **−9.4%** — textbook OVERFIT, ALL top-14 collapse on held-out test. NO lead×price×offset selection rule generalizes. (Contrast ga_profit.py on BINANCE-reconstructed outcomes: there artifact longshot rules showed test +70% "passing" — proving train/test split does NOT catch a systematically-biased label source, only random overfit. Always use REAL redeem outcomes for profit GA.) IMPLICATION: ce25's +2.7% is NOT reducible to a taker entry rule (GA can't find it) → his edge lives in window-selection / value-weighting / or buying below the all-trader-average price — none capturable by a taker. So selection is priced-in for takers; the user's GA idea, done right, CLOSED this path.

**Convergence:** the win-rate line, the profit-map line, AND the GA line all end at the SAME bottleneck. ce25's profit = SELECTION (= binance lead direction + value-weight; we HAVE the signal, [[ce25-selection-decoded]]) × thin +2.7% × volume. As a TAKER the +2.7% is eaten (priced-in). The ONLY lever to fatten it = buy below fair (maker) → exactly what live passive_maker_observe.py is measuring ([[winrate-not-profit-only-edge-is-buy-below-fair]], [[maker-not-real-tested]]). Value-weight refuted (mc_scale, flat EV). So: avoid expensive favorites (≥0.85), and the decisive open question is the maker/execution probe.
