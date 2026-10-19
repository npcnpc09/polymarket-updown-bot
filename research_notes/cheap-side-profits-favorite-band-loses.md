---
name: cheap-side-profits-favorite-band-loses
description: "Our early-taker live losses are ENTIRELY from the EXPENSIVE favorite band (0.75-0.85, -11% ROI); the cheap bands (<0.75) are net POSITIVE. Matches the robust favorite-longshot bias. Candidate: lower PRICE_CAP 0.85->0.75."
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

**KEY (2026-06-08, live early-taker by price band):** our net loss is NOT spread across entries — it's CONCENTRATED in the expensive-favorite band, and the cheap side actually PROFITS:
- 0.5-0.65: n=2, 100% win, ROI+57.5%, +$3.7 (tiny n)
- 0.65-0.75: n=31, 71% win, ROI+1.6%, +$1.7
- **0.75-0.85: n=33, 70% win, ROI−11.2%, −$14.5  ← ALL the loss is here**
- Cheap (<0.75) net +$5.4 vs expensive (>=0.75) net −$14.5. Capping entries at <0.75 would have flipped the day's −$11.20 to ~+$5.4.

**Why it's NOT just one-day noise:** matches the ROBUST favorite-longshot bias from the NEUTRAL 32k-trade test (scripts/neutral_band_test.py): favorites >=0.7 are OVERPRICED (win 84% < price 90%, ROI−11%), cheap/mid bands underpriced-to-fair. Buying a 0.78 favorite that wins 70% = paying above its true prob = −EV; buying a 0.68 side that wins 71% = +EV. Same edge ce25 harvests (buy cheap, avoid expensive favorites — [[ce25-selection-decoded]]) and consistent with eebde's favorite-loading being inaccessible to us ([[eebde-is-spread-maker-not-directional]]).

**CANDIDATE IMPROVEMENT (data-supported, NOT yet validated):** lower the early-taker PRICE_CAP from 0.85 to ~0.75 — only take the cheap/mid side, skip the overpriced favorites. DISCIPLINE: do NOT declare victory in-sample — TODAY's 'confirm-15s' tweak looked +12pp in backtest and FORWARD-FAILED live (85%→67%, [[early-taker-probe-live]]). Forward-validate the 0.75 cap before believing; it also cuts ~half the trades and the cheap entries have lower win rates (cheap=early=less-confirmed, the timing tradeoff from win_by_timing.py). User wants to harvest the cheap side via TAKER (select sides that are already cheap), NOT via maker (maker gets adverse-selected cheap fills — [[maker-not-real-tested]]).
