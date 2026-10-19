---
name: weather-trader-437f-analyzed
description: "0x437f Shanghai-weather trader — COPY-TRADE REFUTED 2026-07-03 (BUY gaps 9-13c = his own price impact in micro-books); net assets = sell capability; only path = own forecast model"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 916a529c-1bc3-4803-a10c-1e88d28c8e6d
---

**COPY-TRADE VERDICT 2026-07-03: DEAD.** Probe caught his Shanghai-morning session: BUY copy_gaps +9.3/+12/+12.7/+13c (avail depth 8-29sh, detection 7-22s fast). NOT latency — his $30-90 orders sweep the entire cheap side of these micro-books, ask reprices +10c within seconds. "His edge IS the entry price" CONFIRMED. Viability ceiling ~3-5c/leg (backtest: 3c=+10.6% ROI, ~5-6c=zero) -> 9-13c deeply -EV. Executor's 3c tax gate correctly skipped ALL (live bot would never trade). Net assets kept: sell_helper capability. Only remaining weather path: BUILD OWN forecast model (NOAA/ECMWF public), rest orders ahead of him instead of chasing.

Account 0x437f1c745a4abd87d5a9a2c61294139d86005b95, analyzed 2026-07-02 (data-api activity, 1912 events, 05-23..07-02, ~40d). Data: scratchpad acct_437f.jsonl, script analyze_437f.py (data-api needs User-Agent header or 403).

**What he does:** trades ONLY "highest-temperature-in-shanghai-<date>-<N>c" daily markets (multiple strikes/day). 1860 trades, $62.7k volume, median trade $12 (mean $34, max $865). BUYs median price 0.368 (43% below 0.30) = buys underpriced temperature strikes using (presumably) public weather-model forecasts (ECMWF/GFS) vs non-meteorologist crowd pricing. **SELLs on convergence (1023 sells vs 837 buys, only 1 REDEEM in 40 days)** — takes profit when market moves to his forecast, does NOT hold to settlement. Side income: 23 liquidity REWARDs + maker/taker rebates + 9 SPLIT/MERGE (occasional two-sided arb). **Est. net PnL +$5,161/40d ≈ $130/day, ~8% gross margin** (approx = sell+redeem-buy; open-inventory edge effects unquantified).

**Why it matters (lesson):** the fat PM edges are information advantages in niche forecastable markets priced by amateurs — NOT microstructure racing in the hyper-efficient crypto books (our 3c/sh regime-fragile edge). Weather = public accurate models + inattentive crowd = textbook case. Zero correlation with our crypto updown book.

**Copy-trade caveats (quant):** his edge is substantially IN the entry price on THIN books (median $12 trades => tiny depth); blind mirroring pays worse entries + can't absorb extra size + needs a sell leg (our engines are buy-and-hold-to-settle; selling was approval-gated). Alternative with no latency dependency: replicate the edge directly from free forecast data (NOAA/ECMWF) vs market prices.

**Copy BACKTEST (past week 06-25..07-02, FIFO round-trips + resolution-settled inventory):** his week +$1,549 (27.2% ROI on buys!); copy scenarios: 1c/leg +$1,249 (21.4%), 2c +$950 (15.8%), 3c/leg still +$654 (10.6%) — edge is thick, robust to slippage. Caveats: assumes full-size fills at his-price+slip; one hot week; needs sell leg. Verdict pivot = measured live copy_gap.

**HE IS HUMAN, NOT A BOT** (bot_check_437f.py): trades only Shanghai waking hours (peak 09-15 CST, 0.3% at 00-05 CST), human round sizes (50/5/10/20/100sh), median gap 138s, same-second bursts = single order sweeps. Semi-manual + weather data. => no speed race; 15s polling ample.

**SELL CAPABILITY DONE 2026-07-02:** scripts/sell_helper.py (import: ensure_approvals(cli), sell(cli,token_id,price,size); CLI --check/--approve/--sell). KEY: the old "sell-approval wall" never existed — on-chain isApprovedForAll(proxy, CTFExchange/NegRiskCtfExchange/NegRiskAdapter) ALL TRUE already (UI onboarding set them). place_limit_order(side="SELL") ready to use. Only missing: one end-to-end micro sell test (~$0.2 cost, user approval pending). polygon-rpc.com gives 401; use polygon-bor-rpc.publicnode.com for eth_call.

**EXECUTOR BUILT 2026-07-02 (user: 明天小额验证):** scripts/copy437f_live.py — DRY default / --place real. Mirrors his BUYs with copy-tax gate (skip if ask > his_fill+3c), depth check, ORDER_USD $5, MAX_EXPOSURE $30, DAILY_STOP -$10; exits via sell_with_escalation when he sells (floor his_px-3c), unsold -> hold-to-settle. DRY rehearsal launched 09:05 (logs copy437f_exec_dry.out, data copy437f_live_dry2.jsonl). Process baseline now **9 python / 2 --place**. Tomorrow (~08Z after his Shanghai session): review probe gaps + rehearsal PnL -> user go/no-go -> $0.2 end-to-end sell test -> relaunch with --place.

**DRY copy probe LAUNCHED 2026-07-02 07:39** (user: "先dry跟单两天"): scripts/copy437f_dry.py (pid varies, NO orders), polls his activity every 15s, on each NEW trade snapshots live CLOB book -> data/copy437f_dry.jsonl fields: copy_gap (BUY: ask-his_fill / SELL: his_fill-bid), avail_sz, det_lat_s. Process baseline now **8 python / 2 --place** (+copy probe). Verdict criteria agreed up-front: copyable if mean BUY gap <2c AND avail depth >=$10-20 at detection AND latency <60s; dead if gap >=3-4c. Review ~2026-07-04.
