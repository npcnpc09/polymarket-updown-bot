---
name: reversal-harvest-oracle-gap-refuted
description: "Reversal-harvest / oracle-gap strategy REFUTED with TRUE Chainlink settles (2026-07-10): blind -38%, his real late-cheap fills -20.4%; tight-window 23%/+132% slice real but unreachable (priced by the time visible, unpredictable before)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 916a529c-1bc3-4803-a10c-1e88d28c8e6d
---

2026-07-10, researched as "new strategy #2" after halting cell (reversal regime 7.5%->12-15%). METHOD UPGRADE: graded with TRUE Chainlink settlements via gamma outcomePrices closed=true (slug or condition_ids param; cache files gamma_settle_cache.json / gamma_cid_cache.json in scratchpad) — no more binance-grading or synthetic coin-flip model.

**Findings (2052 DRY cell-band windows, true-settled):**
- Blind buy-the-underdog at entry (ask=1-B+2c): TRUE reversal rate only 6.0% (binance said 7.3%), ROI **-38.4%**, negative in every lead bucket / half / recent day. REFUTED.
- **Tight windows (|settle|<5bps, 13% of windows): underdog wins 23.1%, ROI +131.9%** — the oracle gap is REAL (46/55 binance-vs-Chainlink mismatches live there; Chainlink flips ~17% of tights).
- BUT unreachable: (a) tightness unknowable at entry (ML: price is sufficient); (b) LATE entry when hugging visible -> underdog no longer cheap: 0xb55f's 13,076 REAL late(>=2/3) cheap(<=0.15) fills true-graded = **-20.4% ROI** (1h -39.5%; 0.05-0.15 buckets -80%). The [0-0.05) +60% bucket = 2.8%-win lottery variance, not edge.

**CONCLUSION: oracle gap exists but is PRICED. No reachable version. Do not revisit blind/late underdog tails.** (Echoes: binance-reconstruction-inflates-longshots, ml-reversal-search-price-is-sufficient.)

Context: all live trading HALTED 2026-07-10 by user (cell regime-mismatched: reversal rate 7.5% baseline -> 12-15% since 07-08; wallet $352.49 all-cash; 15m had self-stopped at -$10 daily stop, then 5m stopped by user; killswitch stopped too). Running: wallet_logger + 3 alt_exec DRY + taker DRY + copy + weather = 7 python / 0 --place. Next candidates: leaderboard scan for who profits NOW (our most productive pattern: found ce25/eebde/b55f), weather model (still collecting), regime-adaptive cell resume when reversal rate normalizes.

**Sizing post-mortem (the -$18.40, 2026-07-09 13:35 eth-5m)**: it was the ONLY full-size cell in 2 days — B=0.92 (just under the 0.93 CELL_HI downsize line) + lead 16.4>=14 + roll10=1 (breaker cold) -> --cellshares 20. All neighboring entries were 5sh (B>=0.93 downsized, or outside band). The 4x sizing on the "best" cell is calibrated to the OLD regime (93% win); in the new regime (rev 12-15%) that best cell is where reversals bite hardest — one 20sh reversal = 3 small losses combined. ON RESUME: drop cellshares 20->10, or gate full-size on DRY reversal-rate <10%.
