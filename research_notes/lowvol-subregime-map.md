---
name: lowvol-subregime-map
description: "Within the low-vol calm period, a held-out-validated map of which sub-regimes the cell makes money in vs loses — from real live fills, 2026-06-27. Decision: validate live before changing engine code."
metadata:
  node_type: memory
  type: project
  originSessionId: 8f4a16b0-b790-40ee-819d-682c2f47380e
---

**Built 2026-06-27 from REAL live fills** (bt_lowvol_strategy.py + bt_lowvol_subregime.py), not paper. Triggered by DRY showing we sat out ~8h of low-vol churn that the engine could trade (see [[overnight-stoploss-policy]] softer-bar correction). First cut: in vol<5, **cell is +EV (n=474, 94% win, +$153.81, EV/sh +0.015) but TAKER is −EV (n=119, 81%, −$20.87, −0.035)** — so low-vol = cell-only, taker off.

**WITHIN low-vol, the cell sub-regime map (EV/share):**
- ✅ PROFITABLE: vol **2.5–3.5** (+0.030) and **3.5–4.5** (+0.025); **btc** (Up +0.045 best, Down +0.007); **normal** breaker-state (+0.033); z 2.5–3.5 (+0.015–0.018).
- ❌ LOSING (avoid): **vol<2.5 dead-water** (−0.031; z/ER inflated, tight-call noise — this is the deep-night dead-calm); **breaker active** (roll10>=2 loss-cluster, −0.065 — clusters persist, [[loss-clustering-circuit-breaker]]); **eth Down** (−0.033); vol 4.5–5 edge (−0.008).
- HELD-OUT (60/40): all-low-vol-cell EV decays to +0.001 held-out, but **btc-only stays +0.024 (FULL +0.026/TRAIN +0.028/HELD +0.024)** — btc is the held-out-stable core; eth drags. Excluding deepcalm makes held-out WORSE (−0.026) → keep deepcalm fills.

**Refined low-vol strategy (NOT yet coded):** open cell only when vol in ~2.5–4.5 sweet spot (skip dead-water <2.5 AND 4.5–5), btc-priority, skip eth-Down, stop (not just downsize) during breaker clusters; taker off all low-vol.

**DECISION (user, 2026-06-27): VALIDATE LIVE BEFORE CHANGING CODE.** Don't edit engines yet. Resume-gate refined to require vol in the sweet spot (~3–4.5, not dead-water <2.5) before opening cell; after resume, watch real PnL against this map (btc>eth? eth-Down weak? breaker-period bleed?) to confirm the sub-regimes on real money, THEN decide whether to code eth-Down-skip / breaker-stop / vol-window. EV/sh edges are thin (+0.007–0.024), so live confirmation matters. The dead-water<2.5 finding already explains why staying stopped at the current vol 1.3–2 is correct.

**USER DECISION 2026-06-28 (~22h into the 4th-stop resume-waiting): KEEP THE STRICT GATE, don't loosen.** I showed the 22h flat cost a DRY-paper +$11 (5m)/+$14.5 (15m) — real ~+$3-6 after alt/inflation discount (btc 5m +6.8, eth ~flat; 15m btc actually −20.8) — i.e. the strict gate is over-strict and missed the early-morning sweet-spot stretch (gate_ok subset +$24.65 vs gate_ok=False −$13.50, engine self-gate works). User STILL chose to keep the strict gate: prioritize protecting the near-ATH $402.22 cushion (+$147 vs breakeven) and cleanest entries over maximizing time-in-market for small money. ACTION: STOP re-pitching "loosen the resume gate" via DRY every idle stretch — only revisit if user asks or a materially new situation appears. Keep waiting for a real trend day (2-consecutive same-direction + vol sweet-spot).

**eth-Down LIVE-VALIDATED FINE 2026-06-28/29:** after ~33h flat, resumed on an ETH-led market-down signal (the gate's hard conditions met; "prefer btc" is soft, ETH-led Down撞 the map's weak zone −0.033). Watched real PnL closely — eth-Down did NOT bleed; the run made +$15.31 over ~8.25h ($402.22→$417.53), printed new ATHs $407→421.61, roll10 stayed <=1 the whole time (near-zero losses), then vol-spike-paused at $417.53. LESSON: the eth-Down "weak zone" was in-sample/small — don't hard-block ETH-led signals; the gate's hard conditions (vol sweet-spot + 7m&14m + 2-consecutive + real move) are what matter, "prefer btc" stays a soft tiebreak only. The agonized 33h-flat then resume-anyway call was RIGHT.
