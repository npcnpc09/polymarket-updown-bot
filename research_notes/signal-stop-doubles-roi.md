---
name: signal-stop-doubles-roi
description: REFUTED at scale — signal-stop does NOT help; its value depends ENTIRELY on entry quality. On clean strong-trend entries it barely fires (~neutral); on marginal/whipsaw entries it false-stops and HURTS. No param saves it. The lever is ENTRY QUALITY, not exit. Don't build sell infra for it.
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

**⛔ HEADLINE REFUTED (2026-06-04) — see REFUTATION block at bottom. The "doubles ROI" below was early small-sample (n=76) optimism and does NOT hold at scale. Keep the rest for context, but the conclusion is: signal-stop is the WRONG lever; entry quality is the real one.**

Backtest (`scripts/debug/_dbg_stoploss.py`, n=76 winner-skew fills over eebde btc/eth windows, choppiness-gated entries) comparing exit strategies for the updown maker:
- HOLD to settle (current behavior): **+7.8%**
- PRICE stop (sell if side price drops 10c below fill): **+7.5%** — useless, marginally worse. A 10c price drop is usually noise/whipsaw; it stops out would-be winners.
- SIGNAL stop (sell the instant the UNDERLYING reverses against our side): **+16.5%** — roughly DOUBLES ROI.

**Why:** the −100% losers that drag ROI are windows where the underlying reversed but we held to zero. Exiting at the moment the underlying turns (selling into the then-current PM bid, before it converges to 0) cuts those losses. This is the SAME "manage by the underlying, not by price ticks" insight as eebde's winner-skew — we'd only ever applied it to ENTRY (choppiness gate / cancel unfilled bids), never to EXIT. Exit was the missing half.

**Why:** validates the user's repeated "动态止损 / ATR" instinct — but the form matters: underlying-signal-based, NOT price-based.

**How to apply:** the live winner-skew probe (`winner_skew_maker.py`) dual-logs `pnl` (hold), `pnl_sstop` (NAIVE stop: sell at FIRST underlying reversal) and `pnl_sstop_conf` (CONFIRMED stop: reversal must persist STOP_CONFIRM_SECS=10s before selling).

**LIVE REFINEMENT (2026-06-03, the key correction):** the backtest's signal-stop = NAIVE (first reversal), and that WHIPSAWS in live ticks — Coinbase WS-mid noise-flips trigger it, stopping WINNERS at a big loss (e.g. sol-5m W4/L0: hold +0.31 → naive −1.81; eth-5m W2/L0: hold +0.48 → naive −1.38). The **CONFIRMED stop (10s persistence) is the right exit**: it dodges those whipsaws (held both above at +0.31/+0.48, n_stopped_conf=0) while STILL cutting genuine reversals (real losers cut by both). Tally over ~27 filtered live windows: naive helped 6 / HURT 4; conf helped 5 / HURT 2 (half the whipsaw damage). Aggregate at winner%=76: HOLD −2.6%, NAIVE −9.7% (whipsaw-killed), **CONF −0.3%** (best, ~breakeven). Same real-time-noise lesson as entries — naive signal triggers break live; require persistence/confirmation. ROI tracks entry winner% ~linearly; break-even ≈74-75% winner with conf-stop; overnight/Asia regime runs 64-76% winner. Need active-hours (EU/US) data to confirm conf-stop crosses positive.

**Caveats (don't overclaim):** (1) real selling needs ERC1155 sell approval — we have NO relayer key or POL gas, so we can't actually stop-loss for real yet; (2) real sell fills into the bid during a reversal stampede → more slippage than the 1c modeled, so real ROI sits between +7.8% and +16.5%; (3) still the optimistic 1-min prices-history fill model, but hold-vs-sstop share it so the RELATIVE 2x is robust. See [[fast-maker-strategy-validated]] [[updown-strategy-pitfalls]] [[erc1155-sell-approval-blocked]].

---
**⛔ REFUTATION (2026-06-04) — three independent samples kill the "doubles ROI" claim; signal-stop is the WRONG lever:**
1. **Big-sample winner_skew probe (635 traded windows, all coins):** HOLD −9.1% vs NAIVE −10.0% vs CONF-10s **−9.8%** — the stop is slightly WORSE than hold, not 2×. ~half of windows triggered a stop, mostly false. Only eth improved (+3.2pp); btc/sol/xrp/doge all got worse.
2. **Live realistic taker DRY (multi_window_engine, real PM bid exit + 2s Coinbase 10s-confirm):** the FIRST confirmed stops were 5/5 FALSE — e.g. eth/sol/btc Down all whipsawed UP 6-13bps for 10s (triggering stop), sold at crashed bids 0.29-0.57, then recovered DOWN and WON. hold +$2.80 → stop −$6.25 on those. The optimistic 1-min backtest hides these sub-minute whipsaws + adverse exit prices.
3. **Parameter sweep (`scripts/stop_param_sweep.py`, 880 ce25 windows, binance 1s for precise reversal+confirm, PM prices-history exit; grid STOP_BPS×CONFIRM):** on CLEAN strong-trend entries (|lead|≥8) the stop barely fires (≤4/154 = 2.6%), 0 false stops at ALL params, marginally HELPS at the low threshold (HOLD +106.4% → +109.3% at 6bps/10s) and does nothing at 15-20bps. NO param is a big win.

**UNIFIED CONCLUSION — stop value depends ENTIRELY on ENTRY QUALITY:** clean strong-trend entries (high lead, gated) rarely reverse → stop barely fires & doesn't need to (hold is fine); marginal/ungated entries (low lead) + maker-adverse fills whipsaw constantly → stop false-fires and HURTS. So the lever is **ENTRY QUALITY (only take clean strong-trend windows), NOT a stop-loss exit.** Bonus: clean-entry + hold-to-settle needs NO ERC1155 sell approval — so the [[erc1155-sell-approval-blocked]] wall stops mattering. Do NOT build sell infra for a signal-stop; it isn't the edge. Connects to [[btceth-only-entry-edge]] (favorite-asymmetry fat tail) — the fat tail is reduced by cleaner ENTRIES, not by exits.
