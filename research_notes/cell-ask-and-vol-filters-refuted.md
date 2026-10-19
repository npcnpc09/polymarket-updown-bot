---
name: cell-ask-and-vol-filters-refuted
description: "2026-06-29 cell ask-cap and vol-ceiling entry filters BOTH refuted (in-sample vs OOS disagree on which vol band is bad) — cell losses are irreducible reversal tail, no single-var entry filter survives"
metadata: 
  node_type: memory
  type: project
  originSessionId: 916a529c-1bc3-4803-a10c-1e88d28c8e6d
---

2026-06-29: after two ~$18.6 cell losses (btc 0.94/0.95, 20sh) bled the wallet $443→$414, tested two natural cell entry filters on 195 live cell fills (net +$85.63, 93% win, EV +0.44/trade):

1. **ask-cap (skip cell if ask>0.93): REFUTED** — the HIGH ask band [0.93,0.96) is the PROFITABLE one (n=156, +$95.20, EV +0.610); low band [0.90,0.93) was the loser (n=39, −$9.57, EV −0.245, but only 4 losses = noise). Capping ask would cut winners, keep losers. Opposite of intuition.

2. **vol-ceiling (skip cell if vol30>=6): REFUTED by OOS** — live in-sample said vol[6,9) bad (EV −0.218, n=26) and [4,6) good (+0.585); but DRY held-out (alt_exec_dry.jsonl, btc/eth, bid[0.90,0.95), z>=2.5, n=147) said the OPPOSITE: [6,9) GOOD (+0.147), [4,6) DISASTER (−0.789). The two datasets disagree on which vol band is weak → vol is NOT a robust cell discriminator, it's noise. The in-sample −0.218 was 2 big losses among 26.

EXHAUSTIVE FOLLOW-UP (2026-06-29, user asked to exhaust options): tested 8 entry features (ask/lead/max_lead/persist/accel/z/vol/lead-decay) winner-vs-loser on BOTH live (n=195) and DRY OOS (n=147) — winners and losers are STATISTICALLY INDISTINGUISHABLE at entry on every one. The ONLY real separator is settle_bps (losers median |4.5|bps = tight-call oracle-noise zone vs winners |16.3|bps) but that's the OUTCOME, not observable at entry. lead-momentum (lead2-lead) showed a mean diff but FAILS as a filter (skips 24 winners to catch 2/14 losers). DRY shows cell ~breakeven as pure taker across ALL coins (btc -0.013, sol -0.010, doge +0.020, eth -0.342) → live cell +EV comes from EXECUTION (maker fill below ask), NOT selection; diversification across coins adds no per-trade edge but spreads the clustered-tail variance. EXIT/stop also dead (tight-call losses settle in final seconds, no time/price to exit + sell-approval wall). FINAL: the -$18 cell losses are MATHEMATICALLY IRREDUCIBLE by entry selection — they are the cost structure of the +EV edge (same trade as winners at entry). Only management levers: (1) already-deployed loss-clustering breaker + STOP -30, (2) smaller size = EV-neutral variance cut, (3) diversify across coins (needs live exec-edge validation first, sol cell unvalidated). Do NOT chase entry filters — exhausted.

CONCLUSION: cell losses are the irreducible [[losses-are-reversals-not-direction-errors]] reversal tail — scattered across all ask/vol/coin/side, no single-var entry filter survives. Textbook overfit tell = in-sample and OOS disagree on which band is bad ([[out-of-sample-catches-overfit]]). cell is a high-win/fat-tail strategy (win ~+$1.2, lose ~−$18.6 at 20sh); the ONLY working guards are the already-deployed [[loss-clustering-circuit-breaker]] (didn't fire — losses weren't clustered) + STOP_LOSS −30. Do NOT add cell entry filters. NOTE: 5m combined engine runs with NO volfloor (default 0); 15m uses --volfloor 5. The recurring 2 big losses were unlucky draws, not a fixable regime.
