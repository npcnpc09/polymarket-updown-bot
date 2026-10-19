---
name: fast-maker-strategy-validated
description: "Fast updown maker strategy — backtest/paper looked +EV but RIGOROUS LIVE VERIFICATION (2026-06-02) showed NOT VIABLE: edge is a measurement artifact destroyed by adverse selection + real-time signal degradation. Do not deploy."
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

**VERDICT 2026-06-02 (after live test + instrumented verification): NOT VIABLE. Do not deploy.**
Earlier "+48% paper / +33% backtest" were MEASUREMENT ARTIFACTS. Convergent evidence from a
large-sample prices-history backtest (n=78) AND the live pitfall-detector:
- Signal WR at minute-close = 94% (robust) but NOT tradeable (hindsight-aligned timing).
- Real-time tradeable WR (live, raw OR 45s-confirmed) = ~73-77%, not 94%; confirmation did NOT
  recover it (confirmed 74% @ n=23 ~= raw). Real-time firing on WS-mid spikes degrades it.
- MAKER fills are adversely selected: a resting bid below mid fills mainly when the favorite is
  DROPPING -> filled WR 44% (offline n=9) / live touch 68% vs 94% signal -> maker_EV = -42%.
- At ~0.80-0.86 entry, break-even needs WR>=80-86%; all tradeable paths land below -> negative EV.
  Market prices these favorites efficiently; our model is overconfident. Oracle ruled out
  (Coinbase vs Chainlink agree 98-100%). Cost of finding out: one $2.45 live doge loss.
See [[updown-strategy-pitfalls]], [[updown-resolution-source-chainlink]].

--- original (now-FALSIFIED) write-up kept for context only: ---

Refined version of the fast 5m/15m updown directional strategy (the eebde-style fast
play, see [[whale_0xeebde7a0_favorite_arb]]). Three fixes addressed the exact failure
modes that killed earlier versions:
1. **sigma recalibrated to 0.5 annualized** (was overconfident at 0.6) — calibrate via
   Brier on shadow data (scripts/debug/_dbg_calib_5m_sigma.py).
2. **fair>=0.85 high-confidence filter** — only trade where the model is reliable
   (backtest: fair>=0.85 -> 99% WR; middle buckets overconfident).
3. **tight maker bid B=round(ask-0.02,2)** — only shallow fills, kills the adverse
   selection that crashed the unfiltered version (+75%@n10 -> +0.2%@n43).

**Validation (2026-06-01):**
- Backtest (model_backtest_5m.py, eebde's 14k fills as price oracle): fair>=0.85, n=260,
  99.2% WR, +38.5% maker / +32.7% taker(+3c) EV. Large sample, robust.
- Paper (maker_paper_probe.py, PID 8164): n=107 filled, maker_EV settled at **+48%**
  (from +62%@n56, regressed but did NOT crash), WR_filled 84% vs WR_signal 86%
  (**adverse selection gone** — only 2pp, vs old 10pp). 0.85+ bucket: n=48, 90% WR, +48%.

**The ONE thing still untested = real maker QUEUE fills** (does our resting post_only
bid actually get matched when ask drops to it). Only live money can test this.

**Plan: tiny LIVE maker test ~2026-06-02.** Tool = scripts/maker_live_test.py:
`--scan` (observe, surfaces fair>=0.85 candidates with ~$1 size) and `--place`
(ONE post_only $1 buy, hard cap MAXNOTIONAL=1.10, holds to auto-redeem, cancels if
unfilled at settle). LIVE tightened to fair>=0.85. Surface only candidates with
>=6min headroom so per-trade approval doesn't miss the window.
Blocker resolution: see [[live-trade-permission-mechanism]].
Wallet 0x149200 is COMPROMISED (pk exposed in chat) — tiny only, rotate before scale.
