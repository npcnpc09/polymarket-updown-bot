---
name: scc-strike-crossing-indicator-validated
description: "2026-06-30 SCC (Strike Crossing Count) indicator was REFUTED — its apparent validation was a backtest BUG (1s-fetch helper didn't truncate to entry, counted crossings over ~16min not window-to-entry). With correct computation, winners/losers have identical C (1.04 vs 1.07). NOT deployed (reverted before going live)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 916a529c-1bc3-4803-a10c-1e88d28c8e6d
---

2026-06-30: user demanded a custom indicator from OUR loss mechanism (not borrowed ER/vol). Derived SCC = # times binance price crosses the window-open (strike) before entry. It APPEARED to pass in-sample+OOS+time-split and "caught" the 3 big drawdown losses (C=5,9,6) — I presented it as a breakthrough. IT WAS WRONG.

THE BUG (caught during pre-deployment equivalence check — engine bin_scc gave C=2,2,0 vs backtest 5,9,6): my scratchpad `fetch1s(start,end)` helper returned 1000 1s-bars (~16 min) regardless of `end` — it never truncated to entry. So EVERY SCC value in the "validation" was crossings over ~16 minutes (past settlement), NOT over window-open->entry. The C>=4 "disaster zone" was an artifact of counting 16 min of noise crossings.

CORRECT RECOMPUTE (truncated to [window_open, entry], DRY n=152): C among WINS median 1 / mean 1.04 ; C among LOSSES median 1 / mean 1.07 — IDENTICAL, no separation. Buckets: C>=3 actually had the HIGHEST win-rate (95%), opposite of the buggy version. Signal does NOT exist. SCC REFUTED.

OUTCOME: engine edits (SCC_K param, bin_scc fn, cell downsize gate, scc logging) were ADDED then fully REVERTED before any live run (py_compile clean, 0 scc refs). Real money never traded on it. LESSONS: (1) "first signal to pass everything / too clean" is a RED FLAG — I should have verified the tool before celebrating ([[backtests-untrustworthy-even-realistic-crossval]] [[out-of-sample-catches-overfit]]). (2) Verify backtest plumbing (does the fetch/window actually cover what you think?) — the equivalence check between deployed code and backtest is what caught it; always do it before live. (3) Still NO validated entry/regime indicator for cell losses; the irreducible-reversal-tail conclusion stands ([[cell-ask-and-vol-filters-refuted]]). Only validated protection remains [[wallet-killswitch-and-halt]] + unconditional smaller cell sizing. Trading still HALTED.
