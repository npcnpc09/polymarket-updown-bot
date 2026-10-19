---
name: maker-price-band-sweet-spot
description: SIGNAL QUALITY (max_lead/choppiness/early_flips), not price, is the maker differentiator — live 2/2 wins at price 0.35 AND 0.90. Do NOT add a price band. (Paper had suggested a 0.80-0.92 band — overturned live.)
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

**LIVE (2026-06-03) — do NOT add a price band; SIGNAL QUALITY is the differentiator.** The validated executor (btc/eth+5m+early_flips≤1+choppiness, NO price band) took 2 real fills: #2 btc Up@**0.35**, #3 btc Up@**0.90** — both clean strong trends (max_lead≈35bps, early_flips=0). Net by WALLET = **+$0.70** (57.58→58.28), i.e. ~breakeven/thin-positive. The filter correctly fired in trend and abstained 1.5h in chop; a cheap (0.35) and an expensive (0.90) fill both being taken shows the differentiator is SIGNAL QUALITY, not price — a price floor/ceiling would wrongly skip valid signals. **CORRECTION/LESSON:** I first claimed "2/2 wins +$3.75" by trusting the probe's `convU` (PM-mid≥0.5) resolution heuristic — that was wrong (real morning result ~+$0.70). FIXED: executor now resolves via the Up-token prices-history (last value ≥0.90=Up won / ≤0.10=Down won), persists post-settle unlike gamma. VALIDATED afternoon run: computed +$0.85 EXACTLY matched wallet $58.28→$59.13. **KEY OPERATIONAL FACT: auto-redeem LAGS ~5 min** — reading the wallet right at settle shows buy-cost-deducted-but-not-yet-redeemed (looks like a loss); wait ~5 min and it catches up. So: trust the prices-history `computed` PnL (now reliable); the wallet confirms after the redemption lag. Twice today I nearly mis-concluded a loss by reading the wallet too early — WAIT for redemption before judging. Real live tally with the fixed executor: high-price fills Up@0.95 (+$0.25) and Up@0.88 (+$0.60) both won (small wins, favorite asymmetry). Wallet now ~$59.13.

Mined the "what makes a winning entry / what's ~100% certain" question two ways.

**1. Certainty frontier (Binance, 3618 btc/eth 5m windows, 7d) — UNCONDITIONAL win-rate of the leading side by (minutes-remaining × |lead|bps):** lead≥20-30bps with ≤2min left → 99-100%; 3min left needs ≥50bps for ~100%; 4min+ needs ≥50bps for 95%. (The "1min remaining = 100% for any lead" row is a look-ahead artifact — outcome proxy = last 1m candle, same timestamp; ignore it.) So bigger lead + closer to settle = more certain. This is eebde's "load the winner late at 0.99" play.

**2. But certainty is PRICED IN, and as a MAKER it inverts at the top.** Segmenting our paper fills by entry price (= market-implied prob): edge = win% − price:
- price <0.65: win49/implied56 → −6pp (coinflip, −EV)
- price 0.65-0.80: win71/73 → −3pp
- **price 0.80-0.92: win94/87 → +7.6pp, ROI +8.7% ← THE SWEET SPOT**
- **price ≥0.92: win66/95 → −29pp, ROI −31% ← TRAP**

**Why the top inverts (key maker insight):** the certainty frontier is the UNCONDITIONAL win-rate, but a maker's fills at ≥0.92 are ADVERSELY SELECTED — a taker only sells you the "near-certain" favorite at 0.94 when they have info it's about to REVERSE (dumping the soon-to-lose side on you). So our high-price fills are disproportionately the reversers → 66% not 99%. This is the mechanism behind the favorite-asymmetry / "win small lose big" all along, and it's why real-test #4 (Down@0.94) was a trap (luckily unfilled). By max_lead: 10-20bps → −8.7pp (market overprices weak leads), ≥35bps → +1.3pp.

**How to apply:** target maker fills in the **0.80-0.92** band; HARD-AVOID ≥0.92 (adverse-selection trap) and <0.80 (coinflip). Add this price-band gate to real_maker_test on top of the [[btceth-only-entry-edge]] filter (btc/eth+5m+early_flips≤1+choppiness) and [[signal-stop-doubles-roi]] exit thinking. Certainty ≠ profit; profit = win% > price, which lives in 0.80-0.92. See [[updown-strategy-pitfalls]].

**BACKTEST-TRAP LESSON (2026-06-03, 3497 btc/eth windows, 3218 fills):** a large-sample backtest that "fills" at the prices-history value at the late minute showed ABSURD edge at EVERY band, biggest when cheap: <0.55 → win91%/price45% = +46pp/+$0.47 per $1; <0.80 → +18pp; ≥0.96 → +2pp. This is FICTITIOUS — it assumes we buy a 91%-winner at 0.45, but nobody sells a winning position cheap except adversely (info it's about to reverse). The crude "fill at history price" model can't represent maker fill availability or adverse selection, so it massively overstates. It CONTRADICTS the realistic-fill paper probe (which required ask≤bid and showed the ≥0.92 trap). Takeaways: (1) the CERTAINTY is real and confirmed at scale (leading side wins 90%+), but the EDGE-vs-price is NOT capturable as a maker — same wall as fast-maker NOT VIABLE ([[fast-maker-strategy-validated]]: real-time signal 77%, maker fills adversely selected 44-68%). (2) The more a backtest's apparent edge depends on the fill price, the more its fill model must be trusted over the number — prefer realistic-fill (ask≤bid) sims and LIVE over crude backtests. The validated live executor placing eth Up@0.61 and NOT filling is the truth in miniature: cheap bids don't get hit.
