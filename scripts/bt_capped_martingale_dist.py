"""bt_capped_martingale_dist.py — exact outcome distribution of the 'capped' recovery:
you just took a -$18 cell air-pocket; now do K=3 cell trades at 100sh @~0.92, then back to 20sh.
Shows the full distribution (not just mean), incl P(end up WORSE than the -$18) and the ruin tail, at a
range of post-air-pocket cell loss rates. Also: does 'after a loss' add anything vs 'always 100sh'?"""
from math import comb
WALLET = 280.0; AIRPOCKET = -18.0; B = 0.92; WIN = 1-B; LOSE = -B; SH = 100; K = 3
def dist(p):
    print(f"\n  post-air-pocket cell loss-rate p={p*100:.0f}%  (normal cell ~4-5%; elevated after a loss):")
    ev_trade = (1-p)*WIN*SH - p*B*SH
    rows = []
    for k in range(K+1):  # k losses out of K
        prob = comb(K, k)*(p**k)*((1-p)**(K-k))
        pnl3 = (K-k)*WIN*SH + k*LOSE*SH   # the 3 recovery trades
        net = AIRPOCKET + pnl3            # incl the original air-pocket
        rows.append((k, prob, net))
    for k, prob, net in rows:
        bankroll_hit = net/WALLET*100
        print(f"    {k} of {K} lose: prob={prob*100:5.1f}%  net(incl -$18)=${net:+7.1f}  ({bankroll_hit:+.0f}% of wallet)")
    ev_net = AIRPOCKET + K*ev_trade
    pworse = sum(prob for k, prob, net in rows if net < AIRPOCKET)   # ended worse than just eating the -18
    pbig = sum(prob for k, prob, net in rows if net <= -80)
    print(f"    => EV of the 3 recovery trades = ${K*ev_trade:+.1f} (per-trade ${ev_trade:+.1f}); EV net incl air-pocket = ${ev_net:+.1f}")
    print(f"    => P(end WORSE than just accepting -$18) = {pworse*100:.0f}% | P(net <= -$80, ~30% of wallet) = {pbig*100:.1f}%")

print("=== 'capped' recovery: -$18 air-pocket, then K=3 cells @100sh, then back to 20sh ===")
for p in (0.05, 0.08, 0.10):
    dist(p)
print("\n=== does 'after a loss' add edge vs 'always 100sh'? ===")
print("  per-trade EV is the SAME function of win-rate either way — the trigger adds NO edge.")
print("  AND post-loss loss-rate is HIGHER (clustering), so 'after a loss' uses the WORSE p, not better.")
print("  So 'recover the air-pocket' is an illusion: you're just making a bigger +EV(maybe) bet at a")
print("  worse moment, with a fat left tail. The -$18 is SUNK — correct size depends on EV+bankroll only.")
