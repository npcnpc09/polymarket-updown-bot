---
name: confirmed-strengthening-maker-first-positive
description: "REFUTED BY REAL MONEY (2026-06-10). User's insight (maker bids on CONFIRMED-STRENGTHENING favorites, fill on a pullback) looked +EV in the PASSIVE probe (win 87-90%, EV +0.04 to +0.09/sh, 27 windows) but a real-money test showed passive's 87% was front-of-queue OPTIMISM: real fills won only 1/4=25%, real PnL -$10.30. The pullback that actually fills a resting bid IS the start of a reversal = adverse selection passive can't capture. Maker does NOT escape adverse selection even on strengtheners. Lesson: passive overestimates, only real money is truth."
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

2026-06-10. User insight (after early-weak maker failed at 17% win): eebde places early then ADDS on the strengthening trend; the adds fill on temporary pullbacks within the uptrend and still win. Tested in 3 stages:

1. PASSIVE probe (passive_maker_observe, confirmed-strengthening: lead>=8 AND growing, bid at mid-D, check if real ask pulls back to fill + win). Looked GREAT: 27 windows, fill-win 87-90% (= backtest 89%), EV +0.04 to +0.09/sh across tiers, deeper=better. Backtest (backtest_strengthening.py, 600 win) confirmed the signal: strengthening favorite wins ~87-89% but is FAIRLY priced (edge~0) — so the apparent +EV was entirely the MAKER DISCOUNT (buying below ask), IF fills capture it without adverse selection.

2. REAL-MONEY test (strength_maker_live.py --place, 5sh post_only at mid-4c on confirmed-strengthening, dedup vs early_taker to avoid double-up): **REFUTED**. 4 real fills, fill-rate 44% (< passive 58%), **fill-win 1/4 = 25%** (vs passive 87%), real PnL **-$10.30**. The 3 losses were reversals.

WHY: a resting BUY bid fills only when price DOWNTICKS to it. On a strengthening favorite, the pullback deep enough to fill your bid (especially behind the queue) is disproportionately the START OF THE REVERSAL — so the FILLED subset is adversely selected (wins 25%, not the 87% of all strengtheners). Passive assumed front-of-queue (fill on the first tiny pullback) and so couldn't see this. This is the SAME adverse selection that killed late-static (70%/-EV) and early-weak (17%) and two-sided ([[twosided-maker-adverse-selection-negEV]]) makers — confirmed-strengthening does NOT escape it.

VERDICT: the maker/eebde line is closed for small capital as a taker-of-the-discount. Every maker config gets adversely selected on fill. eebde survives only via scale + continuous-averaging + being a genuine liquidity provider (deep queue, many fills averaging out), inaccessible to us. CONFIRMS the session's recurring law ([[backtests-untrustworthy-even-realistic-crossval]]): passive/backtest overestimates; real money is the only arbiter. Cost of this validation: ~$10 real. Worth it — it definitively closed the last open lever.
