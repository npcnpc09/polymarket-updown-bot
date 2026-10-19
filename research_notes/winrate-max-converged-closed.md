---
name: winrate-max-converged-closed
description: "The win-rate-maximization line is EXPLORED, CONVERGED, and CLOSED (gen1-3 historical evolution). Do NOT re-run win-rate gens — record the converged formula and move on. The objective itself was wrong (see [[winrate-not-profit-only-edge-is-buy-below-fair]]); the NEW line is max-PROFIT."
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

2026-06-09 (user: "成功率如何最高这条你已经探索出来收敛了,记下来,我们探索赚钱最多的策略"). CLOSING this line.

**Converged win-rate-max formula** (gen1→gen3 historical evolution, 600 real-settled btc/eth 5m windows, capital-weighted win = shares-on-winners/total, 3-fold cross-validated): tight base (lead>=8, or 10-12 = fewer-but-better) + strict strengthening (add only if lead grew >=3-5 over base) + heavy-tail pyramid (sizes like [1,8,16] or [1,10,25]) + strong add-gate (lead>=12). Hits **~92% capital-weighted win, ~97% on heavy/>=2-add windows** (= eebde's 97%), stable across folds. Gen-3 top-15 all 90-92% = CONVERGED (differences are noise). The single-shot floor (no adds) = 66%; averaging adds ~25pp of capital-on-winners. Scripts: cache_and_evolve.py + lead-path cache data/lead_paths.json (fetch-once, every gen instant).

**Why CLOSED, not deployed:** capital-weighted win rate is ORTHOGONAL to profit — it piles money on winners, but the winners are expensive (price ≈ win prob). When re-ranked by PROFIT (real price model), this same champion is only +1.2% and the rest negative. See [[winrate-not-profit-only-edge-is-buy-below-fair]]. So the formula is CORRECT for its objective and the objective is the wrong one. Don't re-explore win-rate; don't run more win-rate gens.

**NEW line = max-PROFIT** (this is where effort goes now): profit = Σ shares×(win−price). Average ≈0 at fair prices (market calibrated). Levers to explore: (A) EXECUTION — buy below fair / maker [live passive_maker_observe.py running, the only real-data answer]; (B) CELL AVOIDANCE — skip the −EV expensive-favorite band, keep +EV cheaper cells [[cheap-side-profits-favorite-band-loses]]; (C) PROFIT-PER-WIN × signal-edge — same pp of edge is worth more $ in a cheaper band, but signal is weaker there; find the band maximizing edge×(1/price). Real ce25 fills (real price+outcome) are the gold standard for (B)/(C) — no model, no binance-longshot inflation [[binance-reconstruction-inflates-longshots]].
