---
name: backtests-untrustworthy-even-realistic-crossval
description: "Even a CAREFULLY realistic backtest of the early_taker filter (path cross+confirm, all-trader BUY prices, +1c measured slippage, real redeem outcomes) still overstates by ~0.27/share when cross-validated against our 37 REAL live fills (+0.160 backtest vs −0.107 real). Selection bias (requiring a near-cross buy trade selects winning windows; the no-liquidity skips are the losers) + price optimism (matched 0.677 < real paid 0.729) are INHERENT and uncorrectable without the real-time book. Only LIVE PnL is trustworthy for this strategy."
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

2026-06-09, user insisted "make the backtest simulate reality or it's meaningless." Built realistic_backtest.py: signal/timing from cached binance 1s lead path (cross=first |lead|>=8 in [5,180]s + CONFIRM lead still >=8 at +15s, exactly like the bot), PRICE = real all-trader BUY trade on the leading side near the cross (a BUY trade = a taker lifting the ask = realistic taker price) + measured slippage +1c (live slip_c mean 0.6c/median 1c), no-buy-near-cross => NO FILL (models liquidity), outcome = real redeem (Chainlink), hold to settle, cap 0.85.

Result: realistic backtest n=197, win 84%, avg paid 0.677, **net EV +0.160/share, +$157.8**. CROSS-VALIDATION vs our 37 REAL live taker fills (ground truth): n=37, win 62%, avg paid 0.729, **net EV −0.107/share, −$19.8**.

**The backtest overstates real execution by ~0.27/share.** Causes, all INHERENT/uncorrectable:
1. SELECTION BIAS (the big one): requiring a leading-side BUY trade near the cross to set the price silently SELECTS windows that ended up winning (149 of 600 windows skipped as 'no liquidity' = windows where buying of the leading side dried up = the lead was fading = the reversers/losers). That's why backtest win 84% vs real 62%.
2. PRICE OPTIMISM: matched buy-trade prices (0.677) are ~5c cheaper than what we really pay at the ask (0.729), even after +1c slippage (matched trades include earlier/better fills than the prevailing ask we hit).
3. REGIME: our 37 live fills were mostly the chop stretch (62% win); the backtest spans several days incl. trend.

CONCLUSION: for this updown taker filter, backtests are NOT trustworthy — even a careful realistic one overstates ~0.27/sh because the price/liquidity reconstruction inherently selects winners and gets optimistic prices (we lack the real-time book + "would we actually have filled"). There is NO backtest shortcut; only LIVE PnL counts (the recurring lesson, now PROVEN via cross-validation, not just asserted). The only live evidence (37 fills) = −EV in chop; true cross-regime EV requires accumulating more LIVE fills. Generalizes [[maker-price-band-sweet-spot]] / [[out-of-sample-catches-overfit]]: the fill-model trap survives even confirm+slippage+buy-side+real-outcomes.
