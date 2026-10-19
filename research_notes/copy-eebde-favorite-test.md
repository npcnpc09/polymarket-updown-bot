---
name: copy-eebde-favorite-test
description: "ONGOING (started 2026-06-05) live paper test of copy-trading eebde's heavy-favorite buys as a TAKER — first small sample looks +EV on strong favorites but n too small; collecting more"
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

Testing whether we can COPY-TRADE eebde's heavy-favorite loads (borrow his 82-90% favorite SELECTION, which we can't produce ourselves — all our own entry filters failed OOS, see [[er-and-bband-filters-fail-oos]]) by entering the same side as a TAKER right after we detect his buy via data-api.

**Tool:** scripts/copy_trade_probe.py (OBSERVE-ONLY, no money). Polls eebde's live BUY trades; when he buys a side on a live updown market it snapshots OUR taker cost (current best ask = what we'd pay copying him, INCLUDING data-api detection lag) + his price/size/ttl; at settle resolves (binance) and computes our copy EV at the ask. Output: data/copy_trade.jsonl. Kept alive by watchdog_dry.ps1.

**First signal (51 rows, 2026-06-03 data — SMALL, post-hoc bands, treat as hypothesis only):**
- Copy ALL his buys: 67% win, ROI/trade −2.0% (his cheap underdog hedges drag it down).
- Copy FAVORITE side (his_px≥0.5): 70% win, ROI −0.4% ≈ breakeven.
- Copy STRONG favorite (his_px≥0.6): 90% win, **ROI +7.5%/trade**, n=21.
- "Can we keep up?" — YES on price: our taker ask is only **+0.5-0.9c above his fill** on favorites (data-api lag barely moves it). Underdog side is +5.9c (don't copy those).

**Why it COULD work where our own taker doesn't:** our own taker = 74% selection ≈ breakeven (+2c). Copying borrows his BETTER selection (90% on strong favorites) at a tiny taker premium → potentially +EV. The edge we can't manufacture, we might rent by following.

**EXECUTION FEASIBILITY answered 2026-06-05 (user asked "can we keep up + get a good price?"):** YES on both. His strong-favorite loads are placed EARLY — median ttl at our detection = 208s (3.5min left), 100% have ttl>=30s, so always time to enter. Price slippage our_ask−his_price: median +1c, 55% within 2c (some even negative = we'd buy cheaper), but 18% run away >5c (skip those). Cleanly-followable subset (ttl>=30 AND slip<=2c) = 55% of his strong-favs, and they showed 92% win / +6.4% ROI. So execution is NOT the bottleneck — the open question is purely whether the +EV is real (still in-sample).

**eebde activity is BURSTY (found 2026-06-05):** his last-200 trades spanned 124min (~1.6/min) vs the 7-day avg ~18/min — currently ~1/10 activity, and at that moment 0 of his recent windows were still live. So copy-probe capture rate is HIS-activity-bound: fast in his active bursts, ~0 in lulls. We can only copy when he's trading live windows. Fixed a probe bug (seen.add ran before the gamma/book success check → transient failures permanently blacklisted a window; now marks seen only after a successful capture).

**SIZE-BUCKET finding (eebde 7d, 2823 windows, favorite win% by $ HE loaded on the favorite side):** $0-50 = 44% win @0.36 (these are his cheap UNDERDOG/hedge buys, NOT favorites — never copy, this is what dragged "copy-all" to −EV); $50-150 = 80% @0.72; $150-400 = 85% @0.76; $400-1000 = 73% @0.64; **$1000-3000 = 89% @0.77 → +12c gross edge (BEST)**; $3000+ = 99% @0.93 → only +6c (priced-in). Bigger $ = higher win BUT also higher price, so edge does NOT grow monotonically — peaks at the $1000-3000 conviction bucket, thins at $3000+. Also time-of-day: best UTC 04-06 (82%), worst UTC 01-03 (63-67%).

**FORWARD test of $1000-3000 bucket (scripts/copy_cum_probe.py, started 2026-06-05, in watchdog):** the original copy_trade_probe snapshots only his FIRST >=$20 trade (single-trade size), NOT the cumulative window load — so it CAN'T test the $-bucket. copy_cum_probe accumulates his running $ per (window,side) (dedup by tx), and when the FAVORITE side's cumulative first crosses $1000 it snapshots OUR taker ask = realistic copy entry; at settle records final_cum so analysis buckets $1000-3000 vs $3000+. Output data/copy_cum.jsonl. Both probes run in parallel; rate is eebde-activity-bound (bursty, currently in a lull).

**How to apply / next step:** n=21 strong-favorite is too small and the ≥0.6 cut is post-hoc (classic overfit shape this session keeps hitting). Do NOT believe +7.5% yet. Let the live probe accumulate; re-analyze data/copy_trade.jsonl filtered to his_price≥0.6 & size≥conviction after a few dozen MORE settled rows, split by day for OOS. Only then judge. Latency caveat: backtest/probe captures price-followability but real fill+reaction latency only fully proven by a tiny real-money copy (not yet authorized).
