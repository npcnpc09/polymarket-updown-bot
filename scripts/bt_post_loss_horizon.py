"""bt_post_loss_horizon.py — tests the hypothesis: 'after an air-pocket, the next few/tens of trades have
a LOWER loss probability (so bet heavy)'. Computes loss-rate over the next-N trades AFTER a loss vs the
unconditional baseline. If post-loss loss-rate < baseline -> user right (anti-cluster, bet heavy).
If >= baseline -> losses CLUSTER, post-loss is MORE dangerous (bet LIGHT)."""
import json, re
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
F = []
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl", encoding="utf-8") if l.strip()):
    if o.get("kind") == "entry" and o.get("won") is not None:
        m = re.search(r"-5m-(\d+)", o.get("slug", ""));
        if m: F.append((int(m.group(1)), bool(o["won"])))
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None:
        m = re.search(r"-5m-(\d+)", o.get("slug", ""));
        if m: F.append((int(m.group(1)), bool(o["won"])))
F.sort(); won = [w for _, w in F]; n = len(won)
base = sum(1 for w in won if not w)/n*100
print(f"{n} time-ordered fills | unconditional loss-rate = {base:.1f}%\n")

loss_idx = [i for i in range(n) if not won[i]]
print("=== loss-rate over the NEXT N trades AFTER a loss (vs baseline %.1f%%) ===" % base)
for N in (1, 3, 5, 10, 20, 30):
    rates = []
    for i in loss_idx:
        nxt = won[i+1:i+1+N]
        if len(nxt) >= max(1, N//2):
            rates.append(sum(1 for w in nxt if not w)/len(nxt)*100)
    if rates:
        avg = sum(rates)/len(rates)
        flag = "  <-- LOWER (user right)" if avg < base-2 else ("  <-- HIGHER (clusters)" if avg > base+2 else "  ~ same")
        print(f"  next {N:2d} trades after a loss: loss-rate = {avg:5.1f}%{flag}")

print("\n=== lag-by-lag: P(loss at t+k | loss at t) ===")
for k in (1, 2, 3, 5, 10, 20):
    pairs = [(i, i+k) for i in loss_idx if i+k < n]
    if pairs:
        r = sum(1 for _, j in pairs if not won[j])/len(pairs)*100
        print(f"  k={k:2d}: {r:5.1f}%  (baseline {base:.1f}%)")

# the 100sh risk framing
print("\n=== 100sh sizing risk (regardless of probability) ===")
print(f"  one air-pocket at 100sh @0.92 = -$92 loss. Wallet ~$280, round profit ~$27 over breakeven.")
print(f"  => a SINGLE 100sh air-pocket wipes >3x the entire round's profit. Our validated size is 20sh (-$18).")
