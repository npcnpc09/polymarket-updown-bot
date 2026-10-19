---
name: eebde-full-decode-and-validation-plan
description: "eebde FULLY reverse-engineered on REAL data (2026-06-09): trend-lead favorite + early cheap base + continuous-averaging into STRENGTHENING persisters (value-weighted) = his +18.8% / +$969k. Validation plan: ~$300-500 + continuous-averaging bot. User: stop raising the wallet-compromise topic."
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

**eebde (0xeebde7a0e019a63e6b476eb425505b7b3e6eba30) COMPLETELY decoded & REAL-validated 2026-06-09** (this time NOT binance-reconstruction artifacts — real settlement via REDEEMs, real prices via all-trader trades, real on-chain profit). His full mechanism:
1. SIGNAL = binance lead DIRECTION (trend) — favorite = lead-aligned side. Real: trend-favorite (lead>=5) +14.5% ROI vs NEUTRAL favorite (no lead) −22.5%. The favorite alone is NOT his edge (ce25's was breakeven); the TREND-aligned favorite is.
2. EARLY cheap base entry (~5s, price ~0.67) — real: his favorite avg fill 0.68, median 0.65.
3. CONTINUOUS-AVERAGING into STRENGTHENING persisters: add to the favorite while its lead keeps building. Real (scripts/confirmer_winrate.py, ce25-redeem-settled): the 60s-lead side that STRENGTHENED by 150s wins 94-95% (vs faded 64%, reversed 35%); monotonic by 150s lead strength (8-15→100%, 15-25→93%).
4. VALUE-WEIGHT the strengtheners: heavy positions self-select to persisters = 93-97% win (eebde_load_real: his heavy-conviction side won ~100% in sample; paper sim 97%).
5. Stop adding on wobble; hold to settle; diversify across many windows.
6. Real profit: leaderboard +$969,280 on-chain (~5.5wk → ~$176k/week).

**WHY it can't be single-shot (the key, real-price-validated, scripts/price_of_strengthening.py):** the CHEAP price (0.67) exists ONLY EARLY (before strengthening is known → 80% win, you don't know which will strengthen). The 95% selection is known ONLY at ~150s — by when the price is PRICED-IN (0.909 → only +5% ROI, taker +3%). The market calibrates: you can get cheap-OR-high-win single-shot, both thin. eebde's +18.8% comes from MARRYING them via averaging: cheap-early base on ALL leads (80%, 0.67) + heavy ADD on the ones that then strengthen (95%) → capital concentrated on cheap-bought 95% winners. The averaging IS the edge; it needs multiple buys per window + capital.

**VALIDATION PLAN (user committed 2026-06-09):** inject ~$300-500 → run a CONTINUOUS-AVERAGING bot (scripts/cont_avg_bot.py — base entry + monitor strengthening + value-weighted adds + stop-on-wobble + diversify + hold). High win rate (80-97%) = LOW variance => modest bankroll ($300-500) suffices for validation (unlike ce25's underdog 30%-win which needs big buffer). Run ~1-2 weeks / 250-500 windows for statistical confidence. Honest expectation: modest return at this scale (+$15-50/wk if it works); eebde's big money needs $5-10k+ scale + Kelly. The test = is the averaging mechanism +EV for US on real settlement.

**VALIDATION GATE (user 2026-06-09): DRY validation must SUCCEED before ANY injection. Do NOT inject funds before cont_avg_bot DRY proves the mechanism is +EV for us. No 'let's see' real-money runs on the current ~$130 either.** DRY-success criteria: over ~100+ windows incl. both trending & choppy regimes — heavy/averaged windows (2-3 adds = strengtheners) win ~90%+, overall EV positive, blended avg price reasonable (~0.74). NOTE: for THIS strategy DRY is TRUSTWORTHY (it buys the FAVORITE side where binance reconstruction is reliable — NOT the cheap-underdog band where DRY was artifact-y; and taker fills are predictable ≈ask+1c). So DRY EV here is a meaningful preview, unlike the longshot DRY. z-maker stopped 2026-06-09 (maker couldn't fill — places & cancels, breakeven). Only cont_avg_bot DRY + wallet_logger run during validation.

**USER INSTRUCTION 2026-06-09: STOP raising the wallet-compromise / 'rotate wallet' topic.** Do not bring it up again. (Earlier [[live-trade-permission-mechanism]] / 'pk exposed' caution — user has decided; drop it.)
