"""bt_cell_kelly_size.py — what's the bankroll-appropriate cell size on a $280 wallet (calm regime)?
Kelly for the binary cell bet (pay B per share, win 1-B, lose B) + the CONCURRENCY/correlation reality
(z-maker runs up to MAX_CONCURRENT=3, MAX_PER_COIN=2 cells at once, same-direction = correlated)."""
WALLET = 280.0; B = 0.92; MAXCONC = 3
b = (1-B)/B   # net odds: win 0.087 per 1 risked
print(f"cell entry B={B}, net odds b={(1-B)/B:.3f}, wallet=${WALLET}\n")
print("=== Kelly per-trade (sensitive to win-rate; use FRACTIONAL Kelly because p is uncertain) ===")
print(f"  {'win%':>5s} {'fullKelly%bankroll':>18s} {'1/4Kelly$':>10s} {'1/4Kelly shares':>16s}")
for p in (0.93, 0.94, 0.95, 0.96, 0.97):
    f = p - (1-p)/b              # Kelly fraction of bankroll to STAKE
    f = max(0, f)
    qk = f/4                      # quarter-Kelly (standard for edge/estimate uncertainty)
    stake = qk*WALLET; shares = stake/B
    print(f"  {p*100:4.0f}% {f*100:16.0f}% {stake:10.1f} {shares:16.0f}")
print("  (full Kelly is wildly aggressive for high-win/low-payoff bets AND assumes p is exact; our p is")
print("   an estimate that drops with adverse fill -> use ~1/4 Kelly. Note how shares SWING with a 1-2pp p change.)")

print("\n=== CONCURRENCY reality: z-maker holds up to 3 cells at once, same-direction = CORRELATED ===")
for sh in (20, 30, 50, 100):
    one = sh*B; conc = sh*B*MAXCONC
    print(f"  {sh:3d}sh: one cell=${one:5.1f} ({one/WALLET*100:3.0f}% wallet) | {MAXCONC} concurrent=${conc:5.1f} ({conc/WALLET*100:3.0f}% wallet at once)")
print("  => a single sharp reversal hits ALL concurrent same-side cells together. At 100sh x3 = ~entire")
print("     wallet at risk in ONE window -> one bad reversal = ruin, REGARDLESS of regime.")

print("\n=== bankroll needed to run 100sh prudently (100sh x3 concurrent <= ~25% of bankroll) ===")
need = 100*B*MAXCONC/0.25
print(f"  100sh x3 = ${100*B*MAXCONC:.0f}; to keep that <=25% of bankroll need wallet >= ${need:.0f}")
print(f"  at $280, the matching size is ~{0.25*WALLET/B/MAXCONC:.0f}sh per cell (current 20sh ~ right).")
print("\nVERDICT: calm-regime is the RIGHT time to be bigger, but SIZE is capped by BANKROLL not weather.")
print("On $280, ~20-30sh is the prudent cell (current 20 is fine). 100sh needs ~$1000+ wallet. Scale the")
print("cell size UP as the wallet COMPOUNDS, keeping concurrent risk a constant ~20-25% of bankroll.")
