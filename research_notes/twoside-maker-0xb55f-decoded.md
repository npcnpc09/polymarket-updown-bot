---
name: twoside-maker-0xb55f-decoded
description: "0xb55f two-sided maker DECODED then 4-DAY BACKTEST DEFLATED (-$1,469/$895k breakeven; the 3h +9.5% was cherry; only 1h family +2.3%); twoside_dry low-priority"
metadata: 
  node_type: memory
  type: project
  originSessionId: 916a529c-1bc3-4803-a10c-1e88d28c8e6d
---

0xb55fa1296e6ec55d0ce53d93b9237389f11764d4 "Lively-Authenticity" ($7.1k account) fully decoded 2026-07-06 from 1925 fills / 88 windows (3h sample, all crypto updown 5m/15m/1h, btc/eth/sol/xrp):

**Strategy**: two-sided patient maker. No entry signal — trades EVERY window. Rests tiny BUY clips (median fill $2.73/15sh, clustered orders median $7.5, 1077 orders/3h) on BOTH sides, accumulates all window. Goal = matched Up+Down pairs costing <$1.

**REAL settled PnL** (gamma-verified outcomes, 81 windows): spend $20,768 → payout $22,743 = **+$1,974, ROI 9.5%, 74% windows green** (med +$9.8/win). Decomposition: matched-pair lock = +$1,918 (97% of profit); half-leg residual = +$57 ≈ NEUTRAL. Half-leg rate median 46% — tolerated, not a bleed (cheap-tail legs are lottery tickets).

**Maker evidence**: only 4.5% same-second multi-price sweeps; multi-fill orders nibbled over med 8s (max 222s); 1 TAKER_REBATE in 2000 events; 75% clean-cent prices. Queue edge =早挂+敢在 0.04-0.08 接飞刀, NOT latency. This is the LIVE counterexample to "two-sided dead" — dead was taker-scan (two-sided-arb-dead-at-latency); alive is maker-wait.

**Caveats**: single 3h sample (US Sunday evening, vol returning) — do not extrapolate $16k/day. Fees not modeled. Earlier "-$4.9k cashPnl" read was a biased slice (unredeemed positions = losing legs only; winning legs already redeemed).

**DRY test**: scripts/twoside_dry.py RUNNING since 2026-07-06 01:53 (data/twoside_dry.jsonl, logs/twoside_dry.out). Mirrors: btc/eth/sol/xrp × 5m/15m, join-bid quotes both sides, clip 15sh, MAX_SH 90/side, PAIR_CAP 0.98, hold to settle. Fill model = REAL trade prints (data-api /trades): STRICT (print<quote, lower bound — judge on this) vs TOUCH (print<=quote, upper bound). One fill per side per cycle. Settle=binance (coin-flip tight calls in analysis). Fixed bugs: gamma closed=true needed for resolved outcomes; one-fill-per-batch.

Gate before any real money: STRICT-model net>0 over multi-day + user OK. Related: [[scaled-imitate-eebde-accumulation]], [[two-sided-arb-dead-at-latency]], [[maker-fill-depth-and-latency-truth]].

**2026-07-06 4-DAY BACKTEST (70,461 fills / 3,015 windows / $895k turnover) DEFLATES the 3h sample**: NET **-$1,469 (-0.16% ROI)** binance-graded; coin-flip-neutralized +$7,425 (+0.83%) = structural edge THIN. Daily swings +/-$5k (07-02 -$4,716); halves -5,132/+3,663 unstable. **Only 1h family profitable (+2.3%, +$5,449); 15m -1.2%, 5m -0.8%; eth his bleed (-2.4%)**. Verdict: NOT a money printer - grind edge ~ breakeven-to-+0.8% on huge turnover, brutal variance; our killswitch would kill it day one. The "+$1,974/3h ROI 9.5%" was a lucky Saturday-evening window (same lesson as SCC/flip60: single-period samples do not extrapolate - caught BEFORE real money). twoside_dry v2 (FAV_CAP 0.85, 1.8h) read STRICT -$0.15/TOUCH +$16.65 ~ flat, consistent. If pursued: 1h windows only. Scripts: scratchpad fetch_b55f_full.py + b55f_backtest.py.

**2026-07-07 FILL-LEVEL DISSECTION found the REAL kernel (user pushed: "analyze which trades win, improve on his base" - correct)**: his profit is NOT 0.9+ selection (that was positions-slice bias, RETRACTED; 1h 0.9-1.0 = -0.4%). Real engine = **1h windows, cheap side p<=0.5, early/mid window** (0.1-0.4 buckets +14.8/+34.8/+14.3%; early-cheap +10.5%, mid-cheap +21.0%). 5m/15m cheap tails are bleeds (-18~-56%). Cross-validates ce25 (underdog<0.5 = his profit too). Day-split (fit 07-02/03, HOLDOUT 07-04/05/06): rule C "1h + p<=0.5" FIT +4.6% -> **HOLDOUT +6.4%, cf-adj +$3,032** (holdout STRONGER = cleanest OOS we have seen). Rule avoids all walls: no 0.9+ skill needed, 4 concurrent windows only, slow cadence. twoside_dry **v3 deployed 03:30** (1h word-slugs ET, FAV_CAP 0.50); v2 data archived twoside_dry_v2.jsonl. Next: 1-2d DRY -> micro live probe (user inclined; needs their OK). Scripts: b55f_dissect.py.

**2026-07-08 07:29 MICRO LIVE LAUNCHED** (bypass mode, user OK): scripts/twoside_live.py --place. 1h btc/eth, CLIP 5sh, MAX_SH 15/side, FAV_CAP 0.50, MAX_EXPOSURE $40, DAILY_STOP -$8, post_only pure maker, hold-to-settle never-sell, one-order-per-side + bid-move>=1c cancel-replace (stacking-bug guarded). Wallet at launch $386.04. Baseline now 11 python / 3 --place. PURPOSE = measure DRY->live execution discount (do the 0.13/0.39 cheap-side resting bids actually FILL? = the maker-queue-wall truth). v3 DRY at launch: STRICT +24%/28h. Data twoside_live.jsonl. Watch: fill rate + fill-price vs DRY, and whether killswitch/daily-stop ever trips.

**2026-07-08 LINE CLOSED — stopped after ~4h live (net -$6.05, within -$8 stop).** User probed every improvement angle; each refuted with data, all pointing to the same wall:
 (1) COMPLETE the half-leg? = pay the other ask; binary identity makes pair pnl = -spread ALWAYS (forced_complete.py: DRY 39 half-legs +$1.80 naked -> -$9 to -$18 completed @1-2c spread). Dead (= two-sided-arb-dead-at-latency).
 (2) GATE to chop windows? REFUTED on his 77k fills: his edge is in TREND (+4.0%) not chop (-0.3%). No regime gate.
 (3) BUY the winning (high-success) side? REFUTED HARD: signal-favored cheap fills = -8.6% ROI (-20% at |lead|>=8); the cheap DROPPING side is the only +EV (+0.5%). = winrate-not-profit re-confirmed on 77k fills; the "loser" side IS where the sliver of edge lives.
 (4) Half-leg = pure loss? NO — it's a fair cheap lottery, net ~0 (buy 0.11 win 11% pays 9x = EV 0).
 THE REAL KILLER = VARIANCE not EV (drawdown_test.py): half-leg equity in DRY netted +$1.80 but rode a -$68.55 drawdown first. On our $380 wallet that's 18% + killswitch trips mid-dip before wins recover. So: ~0 EV + deep drawdown = pure downside for a small wallet. His real pair cost is 0.925 (locks 7.5c), our LIVE hit 0.95 — the DRY 0.73 (locking 27c) was the optimism artifact that made DRY look +24%. Reality ~breakeven, matching his 4-day -0.16%. twoside_dry stopped too. Stale orders: none (post_only void at settle; cancel_all empty). Cell (the actual earner) untouched, wallet $378, new highs this week. Baseline back to 9 python / 2 --place.
