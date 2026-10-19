---
name: two-sided-arb-dead-at-latency
description: "The YES+NO<$1 two-sided arb on updown 5m markets was extensively built & tested (05-30/05-31) and is DEAD as a taker at our latency: dislocations persist 0-3ms vs our ~700ms order latency. Don't re-propose the scan-and-instantly-take version."
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

**The 'scan for YES+NO total < $1 and instantly take both legs' arbitrage on Polymarket BTC/ETH updown 5m markets — DONE and DEAD at our latency.** Built extensively 2026-05-30/31 (~18 scripts): real_arb_detector.py (liquidity-gated, walks both legs by shares, latency-aware), ws_arb_observer.py / arb_scanner_observe.py (real-time scan), two_sided_arb_test→v2..v7 (REAL-money tiny, 7 iterations), arb_exp.py (maker-comb), plus arb_sim/backtest variants.

**THE KILLER finding (data/real_arb_episodes.jsonl):** the dislocations ARE real — min_sum 0.94-0.99 (1-6c mispricing), depth ~$20,000 — BUT they persist **dur_ms = 0-3 MILLISECONDS**. Our order-to-exchange latency is **~700ms**. ~200x gap. By the time we scan it and send, colocated HFT bots have taken it in microseconds. The $20k depth is a ~1ms mirage you can see but never hit. The detector was explicitly built to measure "capturable rate (episode duration >= latency budget)" — and it's ~0. two_sided_arb_v7 real-money: only a few trials, never conclusively captured (the latency wall). User re-raised this idea 2026-06-08; it had already been settled.

**The ONLY non-dead variant** (arb_exp.py path): DON'T race-take the arb — be a MAKER on BOTH sides (post resting bids, FIFO-capture incoming SELL flow at our bid, never lift asks), then handle the residual imbalance (complete-at-ask / scratch-at-bid / hold). This is patient two-sided market-making, NOT "scan-and-instantly-take," and it folded into the broader still-open maker question ([[maker-not-real-tested]]). Pure-taker arb needs colocation / sub-100ms execution we don't have on this box ([[disk-constraint]] box).

**How to apply:** if the user proposes "capture the momentary YES+NO<$1 dislocation by scanning and instantly taking," answer: tested, dead at our ~700ms latency (arbs last 0-3ms). The current edge thread is the opposite — NOT latency-racing arb but [[ce25-selection-decoded]] / [[early-taker-probe-live]] (directional early-taker on the binance lead, which tolerates 100s-of-ms latency because the lead persists for seconds, not ms).
