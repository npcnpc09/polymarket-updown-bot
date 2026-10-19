---
name: updown-resolution-source-chainlink
description: "Polymarket crypto up/down markets resolve on CHAINLINK data streams, not Coinbase/Binance — our signal source differs from the settlement source"
metadata: 
  node_type: memory
  type: reference
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

Polymarket's crypto up/down markets (btc/eth/doge/sol/xrp -updown-5m/15m) resolve using
**Chainlink data streams** (e.g. https://data.chain.link/streams/<coin>-usd), confirmed in
every market's `description` + `resolutionSource` field. The description explicitly says
"the price according to Chainlink data stream, NOT according to other sources." All 5 coins
use Chainlink. The data.chain.link REST is rate-limited (429) — not freely pollable.

Our signal pipeline (coinbase_shadow_probe, maker_paper_probe, maker_live_test) uses
**Coinbase** (level2 WS mid + Coinbase candle open). So SIGNAL SOURCE ≠ SETTLEMENT SOURCE.

**Quantified the oracle-mismatch pitfall (2026-06-02, _dbg_source_divergence.py):** Coinbase
vs Binance over 240 recent 15m windows — lead-gap median 1.1bps / p90 2.7bps; up/down
outcome disagreement only 0.8% overall, and 6.2% ONLY in the tightest <5bps bucket (0% for
|lead|>=5bps). Our fair>=0.85 signals fire on ~7-30bps leads, mostly in the zero-disagreement
zone — so oracle mismatch is a SMALL pitfall, dangerous only at very low ttl (where fair 0.85
needs <10bps lead). Avoid ultra-low-ttl entries and it's a non-issue.

Also found: gamma DE-INDEXES settled updown markets by slug within minutes (only the
current/about-to-settle window is queryable) — can't backfill historical resolutions by slug;
must capture them live near settle. Related: [[fast-maker-strategy-validated]],
[[live-trade-permission-mechanism]].
