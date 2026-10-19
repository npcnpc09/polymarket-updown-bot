# polymarket-updown-bot

A retired real-money trading bot for Polymarket's short-horizon crypto "Up or Down" markets
(BTC/ETH/SOL/XRP, 5-minute and 15-minute windows), plus the full research log behind it.

**Status: retired (2026-08). Published for reference and learning, not as a money machine.**
The edge it traded was competed away, and the conclusions below have an expiry date.

## Result

Real wallet, June–August 2026 (`data/wallet_log.jsonl`, one reading every ~5 minutes):

| | Date | Wallet |
|---|---|---|
| Low | 2026-06-07 | $57.04 |
| Peak | 2026-06-29 | $443.36 |
| Final (all cash) | 2026-08-06 | $322.84 |

Roughly $60 → $320 on a small bankroll. Polymarket charged 0% trading fees on these markets at the time.

## What actually made money: the "cell"

`scripts/multi_window_engine.py` — buy the leading side late in the window when the underlying
(Binance spot) has a strong, confirmed lead over the strike, inside a narrow price band, and hold to settlement.
Around 90% win rate, small profit per win, occasional large loss when price reverses.
Guards that proved useful: a loss-clustering circuit breaker, a wallet-level kill switch
(`scripts/wallet_killswitch.ps1`), and a downsize above 0.93.

Why it stopped: per-trade PnL fell from about +$0.41 (June) to −$0.55 (July) while the win rate stayed ~90%
— the thin edge was competed away. Later, the hosting region was geo-blocked.

## What did not work (all tested with real money or out-of-sample)

- Copy-trading the big crypto up/down whales — they are market-making / arbitrage hedgers, not directional.
- Two-sided arbitrage (Up+Down < $1) from a non-co-located box — almost always half-filled.
- Most entry filters (vol ceilings, ask caps, macro regime sensors, ML on engineered features):
  they looked good in-sample and failed out-of-sample. Price alone is close to a sufficient statistic.
- Deep resting maker bids — they get filled on the reversals (adverse selection).

The details, numbers and the mistakes are in `research_notes/` (start with `research_notes/MEMORY.md`)
and `EXPERIENCE.md` (Chinese).

## Layout

```
scripts/          engines, DRY (paper) runners, backtests, analysis scripts (research-grade, not cleaned up)
research_notes/   one note per finding/decision, indexed by MEMORY.md
data/             wallet_log.jsonl - the real wallet curve (ground truth PnL)
EXPERIENCE.md     early field notes (2026-05)
```

Key scripts: `multi_window_engine.py` (cell engine), `early_taker_probe.py` (taker),
`alt_exec_dry.py` (paper runner), `wallet_logger.py`, `redeemer.py`, `sell_helper.py`,
`ws_paper_executor.py` / `ws_arb_observer.py` (arb detection).

## Running

```bash
pip install -r requirements.txt
cp .env.example .env   # fill POLY_PK / POLY_PROXY etc. - never commit it
```

Most engines run in DRY (paper) mode by default; real orders require an explicit `--place` flag.
Scripts were written for a live research loop and contain hard-coded thresholds and paths.
Expect to read the code before running anything.

## Disclaimer

For education only. Not financial advice. Prediction-market trading may be restricted in your
jurisdiction — check Polymarket's terms. You can lose all the money you put in; this bot did lose
money for long stretches. Use at your own risk.

## License

MIT
