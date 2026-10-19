---
name: lol-whale-e100-copyable-but-cold
description: "0xe1000ddb LoL esports whale: REHEATED 2026-08-26 (+$262k/90d, +27.6% ROI; W31 +50%, W32 +19%, W33 -62%, W34 +97%) after the Jun-Jul drought, and scaled ~10x. Still the only copyable whale (gap +/-2%) BUT profit is 117%-concentrated in 3 markets and his median fill is $25 — a proportional copy inverts his edge. Copy gate NOT met (W33 broke the streak). Geo-block makes it academic anyway."
metadata: 
  node_type: memory
  type: project
  originSessionId: 916a529c-1bc3-4803-a10c-1e88d28c8e6d
---

## UPDATE 2026-08-26 — HE REHEATED (re-measured, true-settle)

User asked "转正了没". Re-ran the full grading (data-api /activity 90d + CLOB `closed`/`winner`
per condition, 1140 fills / 75 markets). **Yes — decisively, on the headline numbers:**

| week | dates | spend | PnL | ROI | n | green |
|---|---|---|---|---|---|---|
| W22 | 05-31 | $7.1k | −$7.1k | −100% | 2 | 0 |
| W23 | 06-01 | $24.3k | −$19.9k | −82% | 4 | 1 |
| W25 | 06-15~21 | $29.6k | −$13.7k | −46% | 9 | 5 |
| W27 | 07-02~04 | $33.6k | −$17.9k | −53% | 7 | 2 |
| **W31** | 07-30~08-02 | $437.6k | **+$219.1k** | **+50.1%** | 9 | 7 |
| **W32** | 08-03~09 | $281.9k | **+$53.9k** | **+19.1%** | 30 | 15 |
| W33 | 08-10~15 | $51.9k | −$32.1k | −61.8% | 8 | 2 |
| **W34** | 08-21 | $81.9k | **+$79.5k** | **+97.1%** | 6 | 4 |

90d total **+$261.8k / $947.8k = +27.62% ROI**, green 36/75. Since 08-03 (the last analysis):
**+$101.3k / +24.38%**, 21/44 green. Fill-level ROI (buys, hold-to-settle) last 32d **+38.6%**
(was −3.6% at the 08-03 reading). He also scaled ~10x: monthly spend $72k (Jun) → $98k (Jul)
→ **$951k (Aug)**.

**But the copy gate is still NOT met, and the reasons matter more than the ROI:**

1. **Streak broken.** Gate = 2+ consecutive green weeks AND fill-level ROI >+15%. W31→W32 met
   it; **W33 (−61.8%) reset it**; W34 is only week 1 again. 4 weeks, 3 green — the shape is
   unchanged from the 08-03 diagnosis (rare concentration weeks), he just drew good ones.
2. **CONCENTRATION 117%.** Since 08-03 the top-3 markets = +$118.4k of a +$101.3k total —
   the other 41 markets are **net negative**. Path max drawdown over that stretch −$73.7k
   (≈ −18% of spend).
3. **NEW — proportional copy INVERTS his edge.** Since 08-03: 767 BUY fills, **median $25,
   p90 $1,170, max $32,738**. Profit lives in a handful of huge fills. Scale his book to a
   $322 wallet proportionally and every big winner rounds below the 5-share minimum while the
   small losing tail fills fine. The ±2% copy-gap result was measured at FILL level and says
   nothing about sizing. **Any copy must be usdcSize-weighted (big fills only) — UNVALIDATED.**
4. **Silent 5 days** at time of writing (last trade 08-21 13:13 UTC) — LoL schedule gap; check
   the split/Worlds calendar before treating silence as a signal.

**Correction to the 08-03 record**: that reading logged W31 as +7%; true-settle now gives
+50.1%. W31 (07-30~08-02) sat exactly on that analysis's boundary — likely graded before those
markets settled. So the old "last 10 weeks −$20k" overstated the drought. This run was
verified by re-fetching three dense days with start/end windows (fill counts and USD matched
exactly) and by hand-checking one condition fill-by-fill.

**DECISION UNCHANGED — WATCH, don't copy.** Re-check after W35: two more green weeks + a
usdcSize-weighted copy sim would be the actual green light. Monitor is now a script:
`scripts/e100_whale_monitor.py --days 90 --since <date>` (incremental cache in
`data/e100_activity.jsonl` + `data/e100_markets.json`, prints the table + gate verdict).
Academic regardless until [[region-blocked-canada-cannot-trade]] is resolved — 0 orders can
be placed from this box.

---

## Original entry — 2026-08-03

2026-08-03: user flagged 0xe1000ddb5f5025849765e29d051dfff78f5d4d41 for copy-trade. Analyzed (user correctly pushed back on my premature 10-day "luck" dismissal — he IS genuinely skilled).

**Profile**: pure League-of-Legends (LoL) esports bettor. 219d (2025-12..2026-08), 120 markets, $1.37M spend, TRUE-settle PnL **+$570,084 = +41.7% ROI**, green 50% (asymmetric: wins bigger than losses), 9/13 positive weeks, max DD -$52k. Sizes $608 median / $57k max. Hold-to-settle (few sells). Buys 0.4-0.7 band (mid/favorite). ~40% of fills within 10s (some in-play).

**Copy-gap test (131 fills last 32d, clob price-history at his_ts+lag, +1c slippage, true-settle)**: gap is only **±2%** at 0-300s lag (we even pay slightly LESS at low lag). This is UNIQUE — 437f/095f had 9-13c uncrossable gaps; his esports books are deep enough / his fills don't spike price. **Execution-wise he is the FIRST genuinely copyable whale we've found.**

**BUT — the catch that kills copying NOW**: his +41.7% lifetime is FRONT-LOADED. W21 alone = +$336k. Recent 10 weeks (W22-31) condition-level NET **-$20k** (W22 -100%, W23 -64%, W27 -26%, W31 +7%); last-32d fill-level ROI -3.6%. He's in a profit-drought. Copying mechanically now = chop/losses waiting for a rare concentration week. His 50% win rate + huge single losses (-$91k one market) = fatal variance on our $322 wallet if we enter during a cold streak.

**DECISION: WATCH, don't copy yet.** He's the best copy candidate found (real edge + followable execution) but currently COLD. Re-consider copying only if he returns to sustained profit (e.g. 2+ consecutive positive weeks, fill-level ROI back >+15%). No monitor cron built yet (user said just "观察"); revisit manually. Contrast: [[sports-inplay-whale-095f-uncopyable]] (uncopyable gap), [[weather-trader-437f-analyzed]] (uncopyable gap). This one's copyable but timing-gated. Wallet still $322.84, 0 --place, updown track dead [[updown-niche-saturated-eebde-breakeven]].
