---
name: weather-model-own-build
description: "OWN Shanghai-weather model project (2026-07-03): resolution=ZSPD METAR via Wunderground; pipeline METAR+met.no live; weather_dry.py logging; his strategy = bias-corrected forecast + intraday obs"
metadata: 
  node_type: memory
  type: project
  originSessionId: 916a529c-1bc3-4803-a10c-1e88d28c8e6d
---

PROJECT (user: "逆向出他的策略,我们也自建这套模型", 2026-07-03) — replicate 0x437f's Shanghai-temp edge with our own data, resting orders ahead instead of copy-chasing (copy refuted, see [[weather-trader-437f-analyzed]]).

**Resolution rules (decoded):** market settles on **Wunderground daily max for Shanghai Pudong Intl Airport (ZSPD)** = METAR-based, whole °C, one 1°C bracket per market, event slug `highest-temperature-in-shanghai-on-<month>-<day>-<year>` (YEAR REQUIRED in slug), ~11 strikes/day, endDate 12:00Z.

**His strategy (reverse-engineered, confirmed by live evidence):** (a) day-ahead: buy brackets cheap vs BIAS-CORRECTED forecast (grid models run ~1-2.2C COLD vs ZSPD station: 07-03 obs 33.0 vs met.no grid 30.8 = +2.2C bias); e.g. he bought july-4 34c @0.229 12:41CST, market repriced 0.30-0.31 within hours = the bias edge in action. (b) intraday: watch ZSPD METAR (30-min cadence, public aviationweather.gov) as the max forms 10-15 CST, trade brackets vs crowd lag; he even errs (bought 32c @0.90 at 12:48, METAR printed 33C at 13:00 -> his likely loss).

**Data pipeline (all free, working):** METAR: `https://aviationweather.gov/api/data/metar?ids=ZSPD&format=json&hours=30` (urllib OK). Forecast: met.no locationforecast lat=31.15 lon=121.80 — MUST use httpx (certifi; system urllib cert store broken for met.no) — open-meteo is CONNECTION-RESET-blocked from this box, do not use. Books: gamma events + clob /book.

**Running:** scripts/weather_dry.py (10-min poll, NO orders, log weather_dry.out, data data/weather_dry.jsonl): METAR cur+running max (CST day) + met.no fc max + full strike ladders (bid/ask/depth) + naive_fair v0 (intraday: running_max + hour-decay remaining-warming; day-ahead: N(fc+1.0 provisional bias, 1.5)). SIGNAL? lines logged when fair-ask>0.10. Copy DRY-executor stopped; copy PROBE kept (his trades = Phase C benchmark). Process baseline **9 python / 2 --place** (7 + copy-probe + weather_dry).

**Next:** (1) calibrate bias+sigma from accumulated obs-vs-forecast days (also fetch historical: met.no no archive — use accumulated logging or Wunderground history scrape); (2) validate v0 signals vs his trades timing (would we have bought july-4 34c before/with him?); (3) then small live with resting limit orders (sell capability + sell_with_escalation ready). Books are micro ($10-50/level) — sizes $5-20.
