---
name: jsonl-underrecords-losses-wallet-is-truth
description: "2026-06-29 confirmed the live engines' per-trade jsonl logs UNDER-RECORD losses (missing settlement rows) — only wallet_log total is trustworthy PnL; recent cell analyses (93% win/+$85) are optimistic"
metadata: 
  node_type: memory
  type: project
  originSessionId: 916a529c-1bc3-4803-a10c-1e88d28c8e6d
---

ROOT CAUSE FOUND + FIXED IN CODE 2026-06-30 (not yet deployed): the bug is resolve_up() (multi_window_engine.py ~L269) — it resolves from the PM token price (last>=0.90→Up-won, <=0.10→lost, ELSE→None). On TIGHT-CALL reversals (= most of our LOSSES, settle ~4.5bps) the PM token ends in 0.10-0.90 → returns None → the filled position hit `if up_win is None: pop; return` and was SILENTLY DROPPED (no jsonl row, no stdout SETTLED) → inflated logged win-rate (cell logged 94% vs real ~87%). FIX: on resolve_up None after the 180s wait, fall back to underlying (binance bin_open settle-price vs strike) so the loss is LOGGED; new jsonl field resolved_by ("pm"|"binance"). py_compile OK. Affects only the 2 multi_window engines (cell 5m+15m); taker logs losses fine. Side effect (good): dropped losses now enter s.fills → breaker stream more accurate. Deploy = restart 5m+15m (recommended: apply on the next resume after the killswitch trips, no extra restart).

2026-06-29: investigating a wallet drop ($414→$395) found the multi_window 5m engine PLACED a 20sh CELL loss (#55, btc-updown-5m-1782771000 Down @0.90, reversed ≈ −$18) that has NO row in multi_window_engine_live.jsonl (grep for window ts = zero matches; jsonl jumps 1782770700 → 1782773700, a 9-window/45-min gap). The engine's STDOUT (logs/zmaker_1782700138.out) has the PLACED/FILLED but the SETTLED row never reached the jsonl.

The engine's own stdout SETTLED lines print a wallet reconciliation: "cum computed=$X | WALLET=$Y (true Δ $Z)" — and true Δ runs −$8 to −$47, i.e. the engine KNOWS actual wallet is running worse than its computed tally. stdout had 29 win/3 loss today, so it's not "wins only," but the jsonl drops some settlement rows (esp. around concurrent positions / maker fills).

CONSEQUENCE: the per-trade jsonl PnL is OPTIMISTIC (under-counts losses). ALL recent jsonl-based analyses are affected — cell "93% win / +$85 / EV +0.44" is too rosy; true cell win rate is lower and net worse. Directional conclusions (losses are reversals, indistinguishable at entry, filters fail OOS — [[cell-ask-and-vol-filters-refuted]] [[macro-regime-sensor-built-and-tested]]) likely still hold, but magnitudes were overstated. RULE (reaffirms [[winrate-not-profit-only-edge-is-buy-below-fair]] & "real PnL = wallet only"): trust ONLY wallet_log.jsonl `total` for PnL; reconcile per-trade analysis against wallet + stdout, never raw jsonl alone. Wallet truth on this date: $395, −$48 from $443 peak, −$18 on day, still >$325 stop. OPEN: a jsonl logging bug (placed→settled row dropped) is worth fixing if reliable per-trade analysis is wanted; the hourly health-check is unaffected (it already reads wallet total).
