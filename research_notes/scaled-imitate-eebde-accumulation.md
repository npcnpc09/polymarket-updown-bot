---
name: scaled-imitate-eebde-accumulation
description: "PROJECT INTENT (user, 2026-06-13): once our scale/capital is up, imitate eebde's accumulation model (patient resting bids, many small fills per window, hold to settle, never sell). CONDITIONAL: only valid where our SELECTION is strong (the cell), not broad market — scale enables it operationally but selection is still the gating edge."
metadata: 
  node_type: memory
  type: project
  originSessionId: 8f4a16b0-b790-40ee-819d-682c2f47380e
---

**User intent (2026-06-13, after we quantified eebde's fills):** when our scale is large enough, move toward imitating eebde's style — the patient-accumulation maker model: rest BUY bids priced to fill, accumulate a window position from many tiny fills (his median $9/fill, ~12 fills/window, max 251), hold ALL to settlement, never sell. See [[eebde-is-spread-maker-not-directional]] for the quantified fill structure.

**CRITICAL CONDITION (do not drop this when acting on the intent):** eebde's accumulation is profitable because his SELECTION is 82% win — strong enough to absorb the adverse fills that resting (non-cancelled) bids inevitably take. Our broad-market selection is ~74% (taker) — too thin; accumulating adverse fills there LOSES (this is why value-weighting was refuted as 0-EV for us, [[ce25-selection-decoded]]). The accumulation model only pays where OUR selection is strong:
- **The cell (z-maker 0.90-0.95, 113/113)** is currently our ONLY proven strong-selection region — that is where eebde-style accumulation should be tried FIRST.
- Scale/capital makes the model *operationally feasible* (can deploy more $, absorb variance) but capital was never the bottleneck ([[ce25-selection-decoded]]: min scale ~$150-350, already met) — SELECTION is.

**How to apply when scaling up:** (1) concentrate accumulation in strong-selection cells, not the whole book; (2) the concrete first experiment = relax the cancel-on-adverse INSIDE the cell to raise fill rate toward his model — but cancel is our adverse-selection shield, so BACKTEST first ([[no-filter-without-independent-backtest]]); (3) keep hold-to-settle (we already do); (4) watch fill-rate-vs-size as size grows (book thins above ~30sh per the depth proxy). Current state: cell just scaled 10→20sh 2026-06-13, under validation ([[zmaker-vs-earlytaker-pnl-anatomy]]).
