---
name: cell-hi-0-93-deployed
description: "2026-06-30 lowered CELL_HI 0.95->0.93 in multi_window_engine.py (downsize B>=0.93 cells to 5sh) — favorite-longshot overpricing, validated robust across ALL history (2 independent DRY datasets, full June, n=1816/139 rev). Code deployed but trading still HALTED."
metadata: 
  node_type: memory
  type: project
  originSessionId: 916a529c-1bc3-4803-a10c-1e88d28c8e6d
---

2026-06-30: deployed CELL_HI=float(_argval("--cellhi","0.93")) in scripts/multi_window_engine.py (was hardcoded 0.95). Effect: cell 20sh only for B in [0.90,0.93); B in [0.93,0.95) now NOT in_cell -> base 5sh (still trades, not skipped); B>0.95 still blocked by separate range gate. Revert: --cellhi 0.95.

VALIDATION (all-history backtest, scratchpad/cap_allhistory.py): the [0.93,0.95) zone is favorite-longshot OVERPRICED and robustly -EV across TWO INDEPENDENT datasets in DIFFERENT periods: multi_window_engine.jsonl DRY (B-based, 06-04..08, n=822/81rev: 0.93-0.94 EV-0.039, 0.94-0.95 -0.146) AND alt_exec_dry (bid-based, 06-14..30, n=994/58rev: 0.93-0.94 -0.169, 0.94-0.95 -0.070). POOLED (n=1816, 139 rev, full June): cap@0.93 improves net in ALL 3 time-thirds (+22/+28/+19, total +69, ROBUST); K=0.93 beats 0.92(+55) and 0.94(+36). Equivalence-checked deployed-code-vs-backtest (py_compile OK, sizing table matches: B>=0.93->5sh trades). Cost: downsizes ~46% of cell wins but each high-bid win is ~$1 vs each avoided loss ~$18 (asymmetry favors it).

CAVEATS: DRY sim pnl (sign/ratio robust, magnitude approx). Within EACH single dataset one time-third was negative (helps overall, not every sub-period). LOW-bid (0.90-0.915) EV FLIPS between periods (early -0.16, late +0.15) -> do NOT prefer low-bid; the rule's value is purely cutting the reliably-bad HIGH bid. It catches only ~2 of today's 5 big losses (the B>=0.93 ones); B=0.90-0.92 losses stay full (that's by design, low-bid is the +EV/irreducible-tail zone, caught by [[wallet-killswitch-and-halt]]).

SUPERSEDES the earlier "ask-cap REFUTED (high-ask is the profitable band)" claim in [[cell-ask-and-vol-filters-refuted]] — that was based on LIVE data which UNDER-RECORDS losses ([[jsonl-underrecords-losses-wallet-is-truth]]), making the high-bid band look falsely profitable. Clean all-history data shows the OPPOSITE: high-bid is the worst. This is the FIRST validated cell improvement (consistent with favorite-longshot prior, not a mined fragile signal). Trading still HALTED; this is staged for resume. NOTE re [[ml-reversal-search-price-is-sufficient]]: price IS the only predictor — and CELL_HI=0.93 is exactly a price-based rule, the one lever that survived.
