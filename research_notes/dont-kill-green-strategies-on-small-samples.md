---
name: dont-kill-green-strategies-on-small-samples
description: "FEEDBACK (user, 2026-06-09) — I repeatedly declared LIVE strategies dead from small samples + one drawdown + paper probes, while trusting optimistic backtests. The real-money strategies were GREEN. A drawdown is not a refutation. Default to letting a green strategy KEEP RUNNING to accumulate sample, not killing it then backtesting."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

User: "有时候你的测试案例太少你就拿来当作了结论，事实上我们的zmaker是赚的还没有亏损，early-taker也是赚的只是回撤了一下就没继续了."

VERIFIED on real data (not impression): **early_maker_live** = 76 real settled trades, net **+$3.30**, PEAK **+$26.55** (fills at 0.715/0.655/0.68 — cheaper than taker). **early-taker multi-window arc** = net **+$31**, peak **+$54** ([[true-pnl-baseline]]). **z-maker** = **+$5.90/11h** ([[dont-fund-experiments-with-working-strategy]]). All three were NET GREEN on real money. I killed/dismissed each as "variance / thin / maker can't fill / dead" based on small samples, a single drawdown, or PAPER probes. (The only genuinely-too-small one is the recent early_taker_probe, n=7, −$6.30 — meaningless either way.)

**The bug:** a pessimism double-standard I already flagged in [[maker-not-real-tested]] — I distrust optimistic fill-models but accept pessimistic paper probes; and I let a clean backtest narrative ("selection priced-in") override live GREEN numbers. Real PnL > backtest. ALWAYS.

**Why it matters / how to apply:**
- A drawdown (e.g. +$26 → +$3) is NORMAL variance, NOT a refutation. Do not kill a net-green strategy on a dip.
- Apply EQUAL skepticism to small POSITIVE and small NEGATIVE samples — never "declare death" on a sample too small to "declare victory."
- Default action for a green-but-noisy live strategy = LET IT KEEP RUNNING to accumulate the long-run sample (this IS the "no conclusions without long-run" principle, [[no-conclusions-without-longrun-and-they-expire]]) — not stop it and run a backtest.
- RECONCILIATION (important, not a contradiction): GA proved SELECTION is priced-in at taker prices (−0.2%); the live green came from EXECUTION (cheaper maker/early fills). So the live greens are the live EVIDENCE that the execution/buy-below-fair lever is net-positive (thinly) — the very lever still open ([[winrate-not-profit-only-edge-is-buy-below-fair]], [[profit-map-barbell-and-blind-benchmark]]). I silenced my own best evidence.
