---
name: updown-strategy-pitfalls
description: Catalog of real-world pitfalls found testing the fast updown maker strategy live + with the instrumented pitfall-detector probe (2026-06-02)
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

Pitfalls uncovered taking the fast updown maker strategy from paper to live (2026-06-02).
The original maker_paper_probe HID most of these (no spread/oracle/timing modeling). The
instrumented detector = scripts/maker_paper_real.py (logs lead_bps/ttl/edge/spread/phantom/
touch/through/conv_px/oracle_flip per signal).

1. **Phantom open (BIG — caused the live loss).** Firing in the first seconds of a window:
   the Coinbase open candle isn't finalized, cb_open returns a stale/wrong open -> a phantom
   lead -> wrong direction. The live doge Up loss had fair_Up=0.864 while correct data said
   fairUp=0.34. FIX: only fire when window age >= 120s (open finalized). Detector confirms 0
   phantoms with this rule.
2. **Oracle source mismatch.** Polymarket resolves on Chainlink, we signal on Coinbase
   ([[updown-resolution-source-chainlink]]). Small overall (~0.8% source disagreement) but
   concentrated at LOW lead: a live oracle_flip was caught on a sol 5m signal with lead=9.3bps
   ttl=74s (Coinbase said win, Chainlink resolved loss). FIX: require |lead| >= ~12bps (sources
   agree >=5bps; 12 is safe). This kills most low-ttl 5m signals.
3. **5-share order minimum.** orderMinSize=5 on every updown market -> min order ~$3-4.50 at our
   prices; $1 impossible for resting/maker orders. (Taker/marketable min is ~$1 — that's why
   yesterday's $1 6e1d order worked: post_only=False marketable, not a resting maker.)
4. **Huge edge = model error, not opportunity.** fair-B > 0.15 means model wildly disagrees with
   market; market usually right on fast windows. FIX: edge cap (MARGIN, 0.15].
5. **gamma de-indexes settled updown markets within minutes** — can't backfill resolutions by
   slug; must capture converged market mid just before settle (conv_px).
6. **Thin books are common** — many fair>=0.85 candidates have wide spreads (skip if ask-bid>0.06);
   the real tradeable opportunity set is much smaller than raw signals suggest. (Detector's raw
   spread-skip counter is inflated by per-second re-polling of the same window; dedupe by slug
   before quoting a number.)
7. **Calm-market signals cluster in the oracle-flip zone.** In quiet hours, fair>=0.85 fires
   almost only on 5m / low-ttl / small-lead (6-12bps) signals — exactly the oracle-risky ones.
   Clean 15m big-lead (15-30bps) signals are rare overnight. So opportunity quality is worst when
   activity is lowest.
8. **Adverse selection (hint, n too small).** Early detector: WR_signal ~75% vs WR on
   touch-filled ~50% — filled orders did worse (you fill as the market moves against you). Needs
   a bigger sample to confirm magnitude.

The MAKER FILL MECHANIC ITSELF WORKS (validated live: a 5sh@0.49 post_only doge order rested ~30s
and FILLED). Related: [[fast-maker-strategy-validated]].
