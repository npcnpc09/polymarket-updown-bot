---
name: ce25-reverse-engineering-conclusion
description: "Honest conclusion of the multi-day ce25 reverse-engineering effort (concluded 2026-06-08): we decoded his ACTIONS but NOT his profitable EDGE. His +$268k is real (on-chain) but unattributable to any band we can decode; the edge lives in our data blind spot. Cannot replicate offline."
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

**!!! OVERTURNED SAME DAY 2026-06-08 — WE DID reverse-engineer it, on REAL data. The "we can't / it's artifact" conclusion below was WRONG (premature). The user pushed to get his full on-chain history and it solved everything.** Path: /activity `end=` time-cursor BYPASSES the offset cap → pulled his FULL 7-day history (scripts/fetch_ce25_full.py → data/ce25_full.jsonl, 125,500 records: 118k TRADE + 7,143 REDEEM). REDEEM events = REAL settlement (winning token redeems $1/share), so winner per window is REAL, NOT binance-reconstructed. scripts/real_decode_week.py:
- **His REAL weekly cash flow: bought $1.476M, redeemed $1.524M, net +$47,738/week** (×5.5wk ≈ $262k ≈ his leaderboard +$268k — RECONCILES, data trustworthy).
- **The cheap-underdog edge is REAL (not artifact): real ROI by band <0.2 +33%, 0.2-0.3 +16.7%, 0.3-0.4 +10.7%, 0.4-0.5 +5.4%, monotonic; favorites 0.5-0.8 ≈breakeven.** underdog<0.5: 31% real win, +11.5% ROI, +$42,763 (=90% of his profit). favorite>=0.5: +0.8%, +$8,568.
- **It's the BAND being underpriced (favorite-longshot bias), NOT his secret selection** — he buys the cheap band broadly (52k underdog trades/wk). So it's REPLICABLE; barrier = VARIANCE (needs diversification) + capital. For small capital the best ROI/variance band = 0.4-0.5 (47% win, +5.4%). The binance-reconstruction was NOISY around the real edge (gave +93% one slice, −6.2% another) — I wrongly inferred "no edge" from "noisy reconstruction." LESSON: noisy reconstruction ≠ edge absent; get the REAL data (here: on-chain redeems via end-cursor) before concluding. THE OFFLINE ROUTE WAS NOT EXHAUSTED — I gave up one API-call short.

**[SUPERSEDED — kept for the record] earlier same-day wrong conclusion:** "we did NOT reverse-engineer ce25's REAL strategy; decoded actions not edge; his $268k unattributable; offline exhausted." This was premature — corrected by the on-chain decode above.

**What's CONFIRMED real:** ce25 (0xcE25...) all-time profit = **+$268,403** (Polymarket leaderboard /profit, lb-api, on-chain — NOT binance-reconstructed). Account ~5.5 weeks old → rapid small→large growth via Kelly compounding. The edge is REAL at scale. (Earlier over-skepticism corrected — the user was right it's real.)

**What we DECODED (his actions, reliable from clear-move data):** signal = binance lead direction (win% rises with lead in every price band); he stakes bulk money (73%) on favorites 0.55-0.85 (avg 0.66) but those are thin (+1.2% ROI); his apparent profit engine is cheap underdogs 0.2-0.45 bought LATE (>60s); diversified (1742 underdog trades, ~13/window); value-weights by lead (but mc_scale: value-weight = 0 EV); holds to settle.

**What we COULD NOT decode (his EDGE — the profit-critical piece):** WHICH part actually makes him +EV. Every band we can test shows breakeven/LOSS in our reconstruction: favorite >=0.7 = −11% ([[cheap-side-profits-favorite-band-loses]]); broad cheap-underdog 0.2-0.4 one-day backtest = **−6.2%** (0.2-0.3 = −14%, 22% win < 25% price); the "+93% cheap-longshot-against-lead" was a binance-reconstruction artifact ([[binance-reconstruction-inflates-longshots]]) that FLIPS SIGN between data slices (+93% one slice, −6.2% another = noise, not edge).

**WHY we failed — the edge is in our DATA BLIND SPOT:** (1) no real PM price history (>~1 day, cids only resolvable recent); (2) no real Chainlink outcomes (gamma clears updown markets ~1h after close — returns empty); (3) binance 1m-kline winner reconstruction is LEAST reliable exactly where his profit supposedly lives (cheap/near-coinflip/tight-call windows) and even FLIPS SIGN across slices. His profitable core sits precisely on the data we cannot measure reliably.

**NET POSITION:** his +$268k is real, but its SOURCE is unidentified by us — actions visible, edge invisible, and what's invisible can't be replicated. Our own tiny real-money tests (taker/maker/early-taker/confirm) all came out breakeven-to-slight-loss; wallet ~flat around $135-140 (incl. a ~$55 user injection 2026-06-08). To actually identify his edge would need either better data (real Chainlink trade-by-trade outcomes, his full history) or expensive noisy real-money experimentation on the compromised wallet. Offline routes are EXHAUSTED. Do NOT re-walk the binance-reconstructed band analysis expecting a different answer; the data can't resolve it.
