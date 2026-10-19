---
name: leadfloor-refuted-true-settle
description: "lead>=14 floor REFUTED with true-settle grading (2026-07-12, 2117 windows): reversal rate is lead-INDEPENDENT (~5-6% flat 8-30, WORSE at 30+); floor excluded the MORE-profitable 8-14 band. Was over-fit to binance grading. On cell re-entry use lead>=8 (no floor), cap lead<30."
metadata: 
  node_type: memory
  type: project
  originSessionId: 916a529c-1bc3-4803-a10c-1e88d28c8e6d
---

2026-07-12: user challenged the CELL_LEAD_FLOOR (=14). Tested on 2117 TRUE-Chainlink-settled cell-band windows (z>=2.5, B 0.90-0.95). User was RIGHT — floor adds no value:

TRUE reversal rate by lead bucket: 8-11=5.3%, 11-14=6.0%, 14-20=5.2%, 20-30=6.6%, **30+=8.1%** (worst). Essentially FLAT 8-30, WORSE at extreme leads. Reversal is lead-INDEPENDENT — confirms [[ml-reversal-search-price-is-sufficient]] (only price/bid predicts reversal, not lead or any feature).

Direct comparison (cell PnL @10sh, 5sh if B>=0.93):
- lead 8-14 (EXCLUDED by floor): reversal 5.7%, +$0.20/window
- lead>=14 (we traded): reversal 6.0%, +$0.12/window
The floor was EXCLUDING the more-profitable band. Non-tight: 8-14=2.7%rev/+$0.45, >=14=3.8%rev/+$0.29 — same story.

WHY the floor once "passed" validation: it was graded on binance + coin-flip model, where it looked good by halving tight-call exposure (tight% 18%->9%). But true settles show that tradeoff wasn't worth dumping the whole 8-14 band. Another over-fit-to-binance artifact (cf. SCC, flip60, btcvol gate).

**Also**: cell at lead>=8 (no floor) true-settled = +$318.9 / 2117 windows = +$0.15/window = THIN-POSITIVE, not negative. So cell's edge didn't vanish; [[cell-retired-2026-07-12]] was a variance/capital-preservation call, correct on a $347 compromised wallet, but "floor protects us" was false confidence — retract it.

**On any cell re-entry**: use --cellleadfloor 8 (effectively no floor), keep CLIMAX-SKIP (lead>=30 is the only genuinely-bad zone, -$0.13/win), keep CELL_HI 0.93 downsize, keep downsized shares. The real irreducible drag is tight-call coin-flips (unpredictable at entry) + variance, NOT lead strength.
