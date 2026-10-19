---
name: live-copy-bot-active
description: "LIVE real-money copy bot active since 2026-06-05 — copies eebde's $1000+ favorite cumulative load as a tiny taker. User authorized; strategy NOT forward-validated."
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

**2026-06-06 SWITCHED live strategy: STOPPED the copy bot, STARTED the self-taker** (`multi_window_engine.py --place`, PID varies). Reason: in the recent ~3-6h regime the filtered self-taker (max_lead>=15 + cushion |lead|>=8 + btc/eth 5m only) was +EV (+0.16/order modeled) while copy was ~breakeven; regime is volatile (flips hourly). Self-taker caps: 5sh, conc3, perCoin2, MAX_TOTAL_ORDERS raised 12->40, STOP_LOSS=-15, notional$15. Same autonomous-SDK no-per-order-prompt mode. NOT in watchdog. Copy bot (below) is the prior live strategy, now stopped (its findings/filters still valid). The lead>=5 copy filter forward result: 40 trades, 88% win, ~breakeven (-$1.10), never reached the +0.24 backtest in the bad regime.

**A LIVE real-money bot is running** (started 2026-06-05, wallet $90.24): `scripts/copy_cum_probe.py --place`. It copies eebde's favorite when his CUMULATIVE load on that side first crosses $1000, as a tiny TAKER (crosses the ask). User explicitly authorized "go live, tiny amounts, keep using the compromised wallet 0x149200 (tiny only)".

**Hard caps (preserve):** SHARES=5 (~$4/order), MAX_CONCURRENT=3, MAX_PER_COIN=2, MAX_TOTAL_ORDERS=40, STOP_LOSS=-15 (halts new orders), MAXNOTIONAL=5. Output: data/copy_cum_live.jsonl, log data/copy_cum_live.log.

**Operational facts:**
- It's an AUTONOMOUS bot placing via the polymarket SDK → NO per-order confirmation prompt (bypasses the usual per-call permission gate since orders aren't agent tool-calls). User accepted this when authorizing tiny live.
- NOT in watchdog_dry.ps1 (watchdog's copy_cum_probe check excludes --place) → if it stop-loss-halts or dies, it stays down for review (correct for real money). The OBSERVE-only copy_cum_probe runs in parallel for the clean forward test.
- eebde activity is bursty; bot is idle during his lulls (no $1000+ live-window favorites to copy).

**First 22 live trades (2026-06-05): 86-89% win, real wallet +~$5-6** ($90.24→~$96), tracking the historical $1k-3k=89% well. Asymmetric payoff: avg win +$0.77, avg loss −$3.18 → EV is WIN-RATE-SENSITIVE (+ at 89%, ~breakeven at 80%, − below 83%).

**SLIPPAGE finding + NEG-SLIP FILTER added 2026-06-05:** we pay median +8.4c vs his blended avg (his_avgpx) — because he ACCUMULATES the favorite as it rises (cheap early) while we enter ONCE at the $1000-crossing (high). KEY: slippage SIGN predicts outcome — our_ask > his_avg (paying premium, favorite still strong) = 15/15 win; our_ask < his_avg (we get it "cheap" = favorite has FADED/reversed since he loaded) = 3/6 win, ALL 3 losses here. So negative slippage = buying a reversing favorite = trap. Added filter (--place only): skip copy if ask < his accumulation avg. In-sample n=22 (overfit risk) — observe-only copy_cum keeps UNFILTERED data to validate the filter forward.

**$300 THRESHOLD EXPERIMENT FAILED (2026-06-06):** backtest (7d 1389win + a lucky 12-trade today-slice) said lowering COPY_MIN 1000→300 = +EV (cheaper entry beats lower win-rate). LIVE OOS REFUTED it: $300 got 53% win / −$9.1 / EV −0.60 (n=15) vs $1000's 85% / +0.05. In a CHOPPY regime the early/less-confirmed $300 entries get chopped (favorite not yet established) — confirmation > cheapness in chop. Reverted to 1000. Another in-sample-good/OOS-fail. Wallet bled to session-low $76 during the experiment (was $90 bot-start, $96.69 peak). The whole copy-bot arc: peaked +$6.45, now ~−$13 from bot start / +$18 vs strategy-start $59.

**LEAD FILTER DEPLOYED 2026-06-06 (strongest-validated change of the run — dual-confirmed):** added `LEAD_MIN=5` — only copy if the UNDERLYING (binance) leads his favorite side by >=5bps at copy time (price confirms his direction). Unlike $300 (backtest-only, failed live), this is validated on BOTH: backtest (760 win, +0.18 EV vs no-filter -0.03) AND LIVE OOS (102 real trades: lead>=5 = 92% win/+0.24 EV/n=71; lead<0 = 33% win/-1.28 EV/n=18 = the disaster cluster). Removing the lead<0 trades flips the live bot from -$4.5 to +$18.5. Mechanism: the losses were windows where he loaded a CONTESTED favorite (his avg ~0.46) that the underlying price was moving AGAINST = weak/contested = 33% win. Also 17/20 losses were final_cum<1500 (he stopped loading = weak conviction); the lead<0 windows correlate. Filter is PROTECTIVE (only skips), real-time (we have the price feed), cuts ~30% of windows. Records `leadf` for forward validation. Other strong $1000-moment predictors (backtest): his_avgpx, value-dominance, rate15 (recent loading speed) — all secondary to the underlying lead.

**HONEST RISK STATE (do not forget):** this strategy is NOT forward-validated — $1000-3000=89%/+12c is HISTORICAL 7d + his realized rate; our taker adds spread; copy_cum forward probe had ZERO data when we went live. The whole session proved in-sample signals fail OOS ([[er-and-bband-filters-fail-oos]], [[out-of-sample-catches-overfit]]). Wallet is compromised (pk leaked) — tiny only, rotate before any scale-up ([[true-pnl-baseline]] for baselines: $59 latest-strategy start, $200 original). MONITOR the real PnL (wallet/on-chain), not engine-modeled. If real results diverge from the 89% hope, stop.
