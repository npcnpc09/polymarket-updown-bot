---
name: dont-fund-experiments-with-working-strategy
description: "Process lesson (user was right, 2026-06-09): I bled the live wallet on real-money taker experiments I MYSELF flagged as thin/-EV, while dismissing the z-maker's actual gains as 'variance'. Net: my experiments lost more than the working strategy made. Don't fiddle with what's working."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

**2026-06-09 the user pointed out, correctly and with data: "the money maker made, your taker lost back."** Exact real (on-chain wallet) accounting: z-maker (maker, loads favorite) 06-08 12h→23h climbed $137.04→$142.94 = **+$5.90 over 11h**; my proposed cheap_underdog_probe (taker) 06-09 00h→ = $142.94→$128.52 = **−$14.42**. My experiments lost MORE than the working strategy made.

**The mistake:** I (a) repeatedly dismissed the z-maker's real, steady gains as "favorable-regime variance / breakeven," while (b) talking us into a string of real-money TAKER experiments (early-taker, confirm-tweak, cheap-underdog) — several of which I MYSELF flagged as thin / possibly −EV / "might be zero" — and spending real money on the compromised wallet to test them. Capital preservation lost to my urge to "validate/reverse-engineer ce25."

**Why:** chasing the decode/validation, I violated the simplest discipline — don't fiddle with what's working, don't fund experiments-you-don't-believe-in with a working strategy's gains, especially on a COMPROMISED wallet. A breakeven-to-slightly-positive live strategy that's climbing should be LEFT ALONE unless an experiment has a clear, validated, positive expectation — which none of mine did (I said so myself, then spent anyway).

**How to apply:** (1) When a live strategy is steadily gaining (even if I suspect it's variance), the bar to interrupt it with a real-money experiment is HIGH — the experiment needs a validated +EV, not "let's see." (2) Test thin/uncertain edges in DRY or paper FIRST; only commit real money when the offline/validated case is positive. (3) On the compromised wallet, default to capital preservation; every real-money probe is a withdrawal from a finite, at-risk balance. (4) Don't simultaneously dismiss a working strategy AND spend its gains on speculation — that's the exact double standard the user caught. Related: [[no-conclusions-without-longrun-and-they-expire]], [[true-pnl-baseline]]. The ce25 edge is real ([[ce25-reverse-engineering-conclusion]]) but UN-capturable at our tiny/taker/compromised-wallet scale — that finding cost ~$14 of real money to confirm; it could have stayed paper.