---
name: polymarket-tail-manipulation-thesis-checked
description: "2026-06-29 checked the \"Polymarket end-of-window reversal manipulation\" web thesis — it's trader-driven thin-book tail-harvesting (NOT platform 做局), and our btc/eth cell losses are NOT explained by it (losses in DEEP books, not thin)"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 916a529c-1bc3-4803-a10c-1e88d28c8e6d
---

2026-06-29: user asked to find a web article claiming Polymarket "做局" (rigs) the BTC market for end-of-window reversals (盘尾反转). SEARCHED EN+CN. Findings:

- NO credible source says the PLATFORM/house rigs reversals. Opposite: Polymarket moved price markets UMA→Chainlink Data Streams (Sept 2025) to REDUCE manipulation.
- The real documented thesis = TRADER-vs-trader: in LOW-LIQUIDITY windows, funded actors place large late sell orders to "砸穿支撑" / tip spot price near settlement to harvest the 99%-tail-scalpers. Structural facts: ~15-20% of 5m windows decided in final 10s; thin books let one large order tip the outcome. Multiple CN articles warn against blindly scalping the tail ("one reversal wipes 几十次 profits" = our cell win-small/lose-big structure).
- Mechanistically this would EXPLAIN our unfilterable losses (adversary picks which thin window to hit → not in entry snapshot → why winners/losers are indistinguishable at entry, see [[cell-ask-and-vol-filters-refuted]]).

BUT TESTED ON OUR DATA (cell adepth, n=97 w/ depth, 5 losses): losses are NOT in thin books — loss median ask-depth 1,387 vs win 1,341 (losses if anything DEEPER); the two −$18.8/−$18.6 losses were in depth 1,653/2,841 (deep). So the thin-book manipulation thesis does NOT explain our losses — our reversals are GENUINE BTC moves in liquid books. We're structurally insulated: cell trades ONLY btc/eth = the deepest, hardest-to-manipulate 5m books; the thesis threatens thin alt/overnight markets we don't touch. CONSEQUENCE: doesn't change current strategy. BUT it's a concrete warning + ready defense variable (book depth) IF we ever expand the cell to sol/alts/overnight thin books ([[macro-regime-sensor-built-and-tested]] diversification idea) — gate on adepth there.
