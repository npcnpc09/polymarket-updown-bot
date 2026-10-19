---
name: cell-retired-2026-07-12
description: "Cell strategy RETIRED 2026-07-12 (user call: 'small win big loss, failed'). All live trading OFF, wallet preserved $347.24. DRY keeps measuring so recovery is data-answerable."
metadata: 
  node_type: memory
  type: project
  originSessionId: 916a529c-1bc3-4803-a10c-1e88d28c8e6d
---

2026-07-12: user retired the cell (z-maker) strategy — "小赚大亏, 已经失效, 440→320". All --place engines + killswitch STOPPED. Wallet preserved $347.24 (all cash). Running: wallet_logger + 3 alt_exec DRY + taker/copy/weather DRY = 7 python / 0 --place.

**Honest trajectory** (not a monotonic crash): all-time peak $443.36 (06-29) -> $347.24 now = -$96 (-22%) over 2wk. Path: peak $443 -> $359 (07-01; NON-cell = stacking bug -$24.6 + taker bleed -$20, both since fixed/stopped) -> recovered to $390 (07-07; cell's good week +$30) -> declined to $347 (07-12; reversal regime + the -$18.4 eth + jsonl-under-recorded bleed, real wallet -$22 vs logged -$7 since 07-11 restart).

**Why retired**: cell's structural small-win/big-loss (buy 0.90-0.95 favorite: win pays 5-10c, loss costs 90c) means a few reversals erase dozens of small wins, and it draws down faster than it climbs. Thin positive EV not worth the ±$40/wk variance on a $350 COMPROMISED wallet (capital-preservation directive). Even after downsize (20->10sh, 07-11) and with HEALTHY regime (reversal 1.9%), it still bled ~$22 in a day -> user judged the edge gone in this regime. Manipulation paper (arXiv 2606.31675) was NOT the cause (signature in only 2% of our reversals; our lead>=14 floor already avoids the near-the-money manipulation zone).

**Re-entry gate (data, not feeling)**: DRY (alt_exec) keeps logging cell-band hypothetical PnL. Only reconsider cell if DRY shows a sustained multi-day POSITIVE run at true-settle grading (gamma closed=true) — i.e., the edge demonstrably returns. Do NOT restart on a low-reversal-rate reading alone (07-11 taught us: low reversal != cell profit).

**Now**: pivot to new-strategy research. Best-productivity pattern = leaderboard scan for who profits in the CURRENT regime (found ce25/eebde/b55f/095f this way). Weather model still collecting (weather_dry). See [[reversal-harvest-oracle-gap-refuted]], [[losses-are-reversals-not-direction-errors]], [[winrate-not-profit-only-edge-is-buy-below-fair]].
