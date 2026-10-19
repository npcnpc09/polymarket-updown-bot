---
name: region-blocked-canada-cannot-trade
description: "2026-08-06: Polymarket now GEO-BLOCKS this box (IP <server-ip>, Canada/Ontario). Every live order rejected 'Trading restricted in your region' — 53/53 attempts, 0 fills. Live trading is IMPOSSIBLE until IP/region resolved. Capital safe (can't lose what can't trade)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 916a529c-1bc3-4803-a10c-1e88d28c8e6d
---

2026-08-06: reopened cell (cellshares 5, floor 8) to test if the July DRY->live gap changed. Discovered instead that ALL live orders now fail with **"Trading restricted in your region, please refer to available regions"** — 53/53 place attempts rejected, 0 fills, wallet unchanged $322.84. Box IP geolocates to **Canada, Ontario (<server-ip>)** — Polymarket blocks Canada. This started sometime during our 3-week halt (worked fine through mid-July).

**IMPLICATIONS**:
- Live trading is currently IMPOSSIBLE from this box regardless of strategy — not a cell problem, a platform-access problem. The "cell revival measurement" experiment is moot (can't place orders).
- Capital 100% safe ($322.84 all cash) — can't lose what you can't trade.
- Any future live strategy (incl. copying [[lol-whale-e100-copyable-but-cold]] if he reheats) is blocked until this is resolved.

**TO RESOLVE (user decision, external)**: needs a non-blocked IP/region — VPN/proxy to an allowed jurisdiction, relocate the box, or a different access path. This is a compliance/geo issue, not something to code around silently (do NOT attempt evasion without explicit user direction — geo-restriction bypass has ToS/legal implications; raise it and let user decide).

**Current state**: all --place engines stopped, killswitch stopped, sentinel cron deleted. Running: wallet_logger + DRY probes (alt_exec x3, taker, copy, weather) — these are read-only/DRY and unaffected by the block, keep logging for research. Research (leaderboard/whale analysis via public data API) is UNAFFECTED — only order placement is blocked. So we can keep researching (e100 watch, market scans) but cannot execute live until geo resolved.
