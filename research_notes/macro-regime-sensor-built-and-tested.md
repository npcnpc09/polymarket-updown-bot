---
name: macro-regime-sensor-built-and-tested
description: "2026-06-29 built a macro BTC regime sensor (1h/4h realized vol, vol-expansion, trend-efficiency, 1h trend magnitude from binance klines) — does NOT yield an actionable cell-entry filter (OOS-fails like all entry filters), but fills the real book-level pause/resume gap"
metadata: 
  node_type: memory
  type: project
  originSessionId: 916a529c-1bc3-4803-a10c-1e88d28c8e6d
---

2026-06-29: user flagged "we lack detection of overall BTC market sentiment + volatility dimension." Correct gap — engines log per-window vol30 (=30-MIN realized vol, bps/min, NOT 30s) + btcvol, but no trend-vs-chop / vol-expansion / longer-horizon regime sensor.

BUILT one properly: fetched BTC 5m binance klines covering all 195 live cell fills (12.4d) + 147 DRY cell-replica (15d, independent OOS), computed at each fill's ts: rv1h, rv4h, volexp(=rv1h/rv4h), eff1h(trend efficiency |net|/path), aret1h(|1h return|). Scripts in scratchpad: macro_regime_test.py (live) + macro_regime_oos.py (DRY OOS).

RESULT for per-trade cell filtering: REFUTED, same as every other entry filter. Directional tilt is REAL+partially OOS-replicated (losses lean toward CALM / contracting-vol / lower-1h-trend regimes — consistent with dead-water vol<2.5 & low-vol-z-inflation priors), BUT not actionable: in-sample eff1h<0.4 KEEP EV +0.421 → OOS −0.230; volexp>=1.0 KEEP +0.779 → OOS −0.112. Every threshold's kept-EV turns negative OOS and sacrifices large winner volume to catch ~half the losers. CONFIRMS FINAL: cell losses irreducible by selection at BOTH micro (entry features) AND macro (regime) level. See [[cell-ask-and-vol-filters-refuted]].

BOOK-LEVEL pause/resume backtest (2026-06-29, user said "backtest the macro regime detection first"): tested on ALL 2038 live fills (24.7d, +$269.66, 3 engines aggregated) + 5124 DRY fills OOS. Only candidate bad-regime = rv1h>=15 (high 1h BTC vol): in-sample EV −0.046/79% win (vs +0.174/89% elsewhere). BUT FAILED BOTH validations: (1) TIME-SPLIT — reverses sign across halves: LIVE first-half rv1h>=15 EV −0.167, second-half +0.160 (the −$17.91 was entirely the first-half's bad-vol days, didn't persist; real vol gate held in BOTH halves, this doesn't). (2) OOS — DRY shows rv1h>=15 ≈0 (−0.001), low-vol bucket actually slightly worse. Script: scratchpad/macro_rv1h_validate.py + macro_booklevel_bt.py.

VERDICT: macro regime detection gives NO robust signal at book level either — same fate as per-trade. Continues the iron rule: market-snapshot regime features fail OOS/time-split (ER, flip60, B-band, now rv1h); only validated regime signal reads our OWN outcome stream ([[loss-clustering-circuit-breaker]]). SILVER LINING: the book is +EV across nearly ALL regimes (only in-sample-first-half high-vol was negative, non-persistent) → strategies are ALREADY regime-robust, there is NO regime-vulnerability for a sensor to fix. DECISION: do NOT build a macro regime sensor as a trading-decision input (pause/resume or sizing) — data doesn't support it. The user's flagged "detection gap" is not an actual exploitable hole. Existing regime guards (breaker + STOP −30, both outcome-stream-based) remain the only validated ones. The narrow validated vol gate ([[btc-vol-regime-gate-has-signal]], vol30>=6.5 on TAKER, both-halves-validated) is a different/narrower thing and still stands — no contradiction.
