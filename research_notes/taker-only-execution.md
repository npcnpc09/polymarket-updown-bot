---
name: taker-only-execution
description: "For load-the-winner, use TAKER ONLY — maker is not a second opportunity stream but an inferior/adverse entry for the SAME trade; running both (maker-first-then-taker) is strictly worse. Live taker 8/8, day +$11.02."
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

**For the load-the-winner edge: execute TAKER ONLY. Do not run maker and taker together.**

maker and taker are NOT two opportunity streams — they are two entry methods for the **same** signal-gated trade (both gated by the same ~4.5 qualifying btc/eth 5m windows/hr, which is why their opportunity COUNT looks similar). For a given "underlying trending Up, load Up" window:
- **taker** = cross the ask, fill immediately @~0.80, deterministically acquire the winner.
- **maker** = post bid @0.79 and wait — but in a trend the Up price is rising, so nobody sells the winning side cheap; the bid mostly DOESN'T fill, and when it DOES it's adverse selection (someone with info Up is about to reverse dumps the soon-to-lose side on you → you receive the reverser). Live-confirmed: maker eth Up@0.61 did NOT fill (cheap bid not hit); switching to taker → 8/8 wins. Matches [[maker-price-band-sweet-spot]] / [[fast-maker-strategy-validated]] (maker fills adversely selected 44-68%).

**Why "both together" (maker-first, taker-fallback to save spread) is STRICTLY WORSE — counterintuitive:** the maker bids that DO get hit are the adversely-selected reversers (bad fills), while the genuine winners' bids don't fill so you taker-chase them at a higher price. Net: maker-first selects FOR the bad fills AND makes you pay up for the good ones. Pure taker avoids both traps; its spread cost (~1.5-2.5% of cost) is already netted into the +11% live margin.

maker only pays as **neutral two-sided liquidity provision at scale + rebates** (eebde/ce25 style) — which is −15% for US (no rebate edge, no scale, pure adverse selection). So keep maker as a PAPER probe only (winner_skew_maker, for measuring signal quality), never real execution.

**LIVE taker validation (2026-06-03→04):** TAKER=True executor (btc/eth+5m+early_flips≤1+choppiness gate, prices-history resolution), starting wallet $59.48 → **$70.50, day +$11.02, 8/8 wins**, 21 cumulative live fills. Caveat still standing: a ~10% reversal loss is statistically due and hasn't hit the taker streak yet — don't over-extrapolate 8/8.

**Multi-window vs single-window (frequency lever, NOT yet built):** current executor is SERIAL — while holding one position to settle (~2-5min) it ignores other qualifying windows, capturing only ~half the ~4.5/hr supply. A concurrent multi-window engine would open EVERY qualifying window → ~2x frequency AND ~2x profit, BUT ~Nx CORRELATED tail risk: concurrent positions are all btc/eth direction, so one underlying reversal hits all same-side positions at once (5 concurrent btc Down × −$4 = −$20 together). Multi-window is a profit-AND-risk amplifier; only for a larger, drawdown-tolerant account, and only AFTER rotating the compromised wallet + confirming the single-window taker edge is robust live. See [[btceth-only-entry-edge]], [[signal-stop-doubles-roi]].
