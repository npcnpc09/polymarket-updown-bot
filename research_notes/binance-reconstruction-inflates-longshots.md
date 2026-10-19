---
name: binance-reconstruction-inflates-longshots
description: "Binance-reconstructed win/loss INFLATES the cheap-longshot edge ~7x vs real settlement — a binance!=Chainlink artifact concentrated in near-determined cheap longshots. The +93%/+3008% 'longshot harvest' is a mirage; the real edge is ce25's actual ~+13%."
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

**2026-06-08: the 'cheap underdog against the lead is hugely underpriced' finding is a RECONSTRUCTION ARTIFACT, not a real edge.** Path: ce25_underdog_selection showed his underdog profit is contrarian (cheap side AGAINST the binance lead, 0.21-0.27, +40% ROI). neutral_underdog_validate (all-trader, 16k trades) said it's RAW market-wide (+9 to +17pp edge, ROI +93% deep / +204% <0.2). longshot_scale_oos Monte-Carlo then showed +121% to +3008% returns with ~0% ruin. **Those numbers are TOO GOOD = the signature of an artifact, not an opportunity.**

**PROOF it's an artifact:** ce25's REAL underdog ROI (his actual trades, real money, Chainlink-settled) = **+12.9%**. My binance-1m-reconstructed neutral = **+93.5%**. ~7x inflation = pure reconstruction error. WHY it concentrates in cheap longshots: those are bought LATE (window nearly decided), at 0.11-0.27; the PM price is set on the real-time CHAINLINK-relevant move (correct), but I reconstruct winner via binance 1-MINUTE open@st vs close@st+dur, which is least reliable exactly on near-coinflip endings. The ~28% of "wins" the reconstruction sees that the market didn't price = binance!=Chainlink disagreement ([[updown-resolution-source-chainlink]]), NOT real underpricing. A side priced 0.11 winning 28% would be free money arbitraged instantly; the persistence = it's our measurement error.

**The REAL edge (not the mirage):** ce25 DID make ~+5-13% ROI on underdogs with real money (real settlement) — a real diversified favorite-longshot harvest, but +13% not +93%, at 28-40% win = high variance needing his 1742-bet diversification. mc_scale.py already validated the REAL version (resampled his actual Chainlink-settled trades: +$0.465/trade, diversification smooths, bankroll ~$150-350). Trust mc_scale (real trades), NOT longshot_scale_oos (binance-reconstructed, inflated 7x).

**GENERAL LESSON (applies to ALL our binance-reconstructed backtests):** any backtest that reconstructs updown win/loss from binance klines OVER-states edges that live in near-determined / cheap-longshot / tight-call regions, because that's where binance!=Chainlink and 1m-kline timing error is maximal. Discount reconstructed PnL there; only real-money on-chain settlement (or ce25's real realized returns) is ground truth. Do NOT scale on a binance-reconstructed longshot edge — real fills settle on Chainlink and the underdog loses as the market priced. The whole episode re-confirms 'real fills/settlement only' over reconstruction.
