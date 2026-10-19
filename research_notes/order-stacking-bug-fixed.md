---
name: order-stacking-bug-fixed
description: 2026-07-02 stacking bug — cancel-repost loop put 8 orders on one window (-$24.56); orphaned fills = another under-record source; FIXED
metadata: 
  node_type: memory
  type: project
  originSessionId: 916a529c-1bc3-4803-a10c-1e88d28c8e6d
---

2026-07-02 03:24-03:30: 15m engine placed **8 orders (#21-28) on ONE window** (eth-updown-15m-1782962100 Down): 1x10sh CELL @0.92 + 7x5sh @0.94-0.95, ~$24.6 notional filled, window settled against -> **-$24.56 single-window loss** (wallet 370->345.7, killswitch buffer left ~$4.5).

**Mechanism (multi_window_engine.py):** entry guard was only `slug in s.actives`. The adverse-cancel path (unfilled + lead flips through zero or weakens < THR*0.5) cancels and **pops s.actives[slug]** -> next tick lead is strong again -> slug free -> RE-PLACE. In a whipsawing window this loops every ~14s = stacking. Worse: the cancel checked the poll-lagged `o["filled"]` flag — an order that JUST matched looked unfilled, got canceled(fails silently)+popped -> **ORPHANED position**: real shares held to settle but engine no longer tracks -> never logged (= yet another under-record source; explains some historical jsonl-vs-wallet gaps) while its slug re-entered. Also: repeated placements on the same slug OVERWRITE the same dict key, so perCoin/concurrency caps never saw the stack. Symptom fingerprint in logs: same-slug PLACED bursts + `persist>1` (peak_lead lagging behind lead).

**FIX (deployed 03:57, both engines restarted, pids 5m=2864/15m=7340, logs deploy5_5m/15m.out):**
1. `s.done` set — a slug ever placed is NEVER re-entered (one shot per window; entry guard now `slug in s.actives or slug in s.done`).
2. Adverse-cancel now queries REAL size_matched first; if >0 -> mark filled + hold to settle (log "CANCEL(adverse) ABORTED ... holding"), only truly-unmatched orders get canceled+popped.

Historic "paired same-window entries" in trade lists were milder occurrences of the same loop. [[jsonl-underrecords-losses-wallet-is-truth]] [[cell-leadfloor-16-and-taker-off]]

Killswitch RE-BASELINED 04:04 (user chose: bug loss shouldn't consume strategy-drawdown budget): baseline/peak $345.66, trip-line $315.66, buffer full $30 (was $4.45 to old line $341.21). DD_LIMIT=30/confirm=2 unchanged; hourly-check $325 alert line unchanged. Trip-watcher prompt still cites old resume point $363.42 — actual reference now $345.66.
