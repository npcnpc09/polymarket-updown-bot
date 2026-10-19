---
name: ml-reversal-search-price-is-sufficient
description: "2026-06-30 large-scale ML search (3154 favorites, 239 reversals, gradient-boosting, time-split OOS) — reversal IS predictable but ONLY by the bid price (AUC 0.70); all 13 engineered features ADD NOTHING beyond price (full model 0.64 < market 0.70). Price is a sufficient statistic; no residual edge."
metadata: 
  node_type: memory
  type: project
  originSessionId: 916a529c-1bc3-4803-a10c-1e88d28c8e6d
---

2026-06-30: user (rightly) pushed that AlphaGo doesn't conclude failure on small samples — it scales the search. So I scaled ~100x: all 3 DRY files (12,878 windows, 6 coins) -> favorites (bid 0.85-0.96, z>=2) = 3,154 windows, 239 reversals (7.6%). Trained GradientBoostingClassifier (13 features: bid, abs_lead, z, cvol, btcvol, off, spread, momentum=sign(lead)*(lead2-lead), depth_imbalance, ask_depth, lead2, vol_ratio) with TIME-SPLIT OOS (train first 60/70/80%, test on later windows). sklearn+numpy installed for this.

RESULT (held-out AUC): MARKET (bid alone) 0.68-0.71 | bid-only ML 0.65-0.69 | FULL 13-feature ML 0.60-0.64. The full model is WORSE than the price alone — the extra features are noise it overfits, degrading the bid's own signal on future data. CONCLUSION: reversal IS predictable, but the bid PRICE is a sufficient statistic for it; our engineered features extract ZERO residual predictability beyond price. This is WHY every entry indicator failed ([[cell-ask-and-vol-filters-refuted]] [[macro-regime-sensor-built-and-tested]] [[scc-strike-crossing-indicator-validated]]) — not bad indicator choices, but the market prices reversal efficiently at the 5-min scale and leaves no feature-extractable edge. Not "giving up": the search converged on the true structure (price-locked, like a solved-lost Go position).

THE ONE DATA-SUPPORTED LEVER: since price predicts reversal (AUC 0.70, lower bid -> more reversal; consistent with the 0.90-0.92 band losing vs 0.93-0.95 winning), the only "predictive" knob is PRICE-BASED SIZING within the favorite zone (downsize cell near 0.90, full near 0.95) — NOT feature gates. Candidate to OOS-test next. Protection otherwise stays [[wallet-killswitch-and-halt]] + unconditional smaller cell. Trading still HALTED. Scripts: scratchpad/ml_search.py, feature_search.py.
