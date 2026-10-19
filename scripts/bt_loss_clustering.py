"""bt_loss_clustering.py — is the drawdown a PERSISTENT regime or i.i.d. variance?
Tests temporal clustering of REAL trade outcomes (taker+zmaker, time-ordered):
  1. lag-1 outcome autocorr: P(loss | prev loss) vs P(loss | prev win). >base => clustering.
  2. Wald-Wolfowitz runs test: are win/loss runs fewer than random (=clustering)?
  3. rolling-10 loss-rate: does a hot loss-streak predict the NEXT trades being worse? (circuit-breaker test)
  4. max consecutive losses observed vs expected under i.i.d.
If outcomes CLUSTER -> a 'recent loss-rate' circuit breaker is a real, actionable indicator even though
single losses are unpredictable. If NOT -> the drawdown is variance (one 20sh air-pocket + bunching)."""
import json, math, re, statistics as st
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
F = []
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl", encoding="utf-8") if l.strip()):
    if o.get("kind") == "entry" and o.get("won") is not None:
        m = re.search(r"-5m-(\d+)", o.get("slug", ""));
        if m: F.append({"ws": int(m.group(1)), "won": bool(o["won"]), "pnl": o.get("pnl", 0)})
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None:
        m = re.search(r"-5m-(\d+)", o.get("slug", ""));
        if m: F.append({"ws": int(m.group(1)), "won": bool(o["won"]), "pnl": o.get("pnl", 0)})
F.sort(key=lambda x: x["ws"])
n = len(F); L = sum(1 for f in F if not f["won"]); base = L/n
print(f"{n} time-ordered fills | loss-rate base = {base*100:.2f}%\n")

# 1. lag-1 outcome autocorrelation
pl_pl = pl_pw = npl = npw = 0
for i in range(1, n):
    prev_loss = not F[i-1]["won"]; cur_loss = not F[i]["won"]
    if prev_loss: npl += 1; pl_pl += cur_loss
    else: npw += 1; pl_pw += cur_loss
print("=== 1. lag-1 outcome autocorrelation ===")
print(f"  P(loss | prev LOSS) = {pl_pl/npl*100:.1f}%  (n={npl})")
print(f"  P(loss | prev WIN ) = {pl_pw/npw*100:.1f}%  (n={npw})")
print(f"  base loss-rate      = {base*100:.1f}%")
lift = (pl_pl/npl)-(pl_pw/npw)
print(f"  => clustering lift = {lift*100:+.1f}pp  ({'CLUSTERS (regime persists)' if lift>0.05 else 'no meaningful clustering'})")

# 2. runs test (Wald-Wolfowitz)
runs = 1 + sum(1 for i in range(1, n) if F[i]["won"] != F[i-1]["won"])
nW = n-L; exp_runs = 1 + 2*nW*L/n; var_runs = 2*nW*L*(2*nW*L-n)/(n*n*(n-1)) if n > 1 else 0
z = (runs-exp_runs)/math.sqrt(var_runs) if var_runs > 0 else 0
print(f"\n=== 2. runs test ===")
print(f"  observed runs={runs} expected(iid)={exp_runs:.1f} z={z:+.2f}  ({'FEWER runs=CLUSTERED' if z<-1.96 else 'consistent with i.i.d.' if abs(z)<1.96 else 'more runs=anti-clustered'})")

# 3. rolling-10 loss-rate predicts next?
print(f"\n=== 3. does a hot loss-streak predict the NEXT trade? (circuit-breaker) ===")
for thr in (2, 3, 4):
    after_hot = []; after_cool = []
    for i in range(10, n):
        recent = sum(1 for f in F[i-10:i] if not f["won"])
        (after_hot if recent >= thr else after_cool).append(not F[i]["won"])
    if after_hot and after_cool:
        print(f"  prev-10 had >={thr} losses: next loss%={sum(after_hot)/len(after_hot)*100:5.1f} (n={len(after_hot)})  | "
              f"<{thr}: next loss%={sum(after_cool)/len(after_cool)*100:5.1f} (n={len(after_cool)})")

# 4. max consecutive losses vs i.i.d. expectation
mc = cur = 0
for f in F:
    cur = cur+1 if not f["won"] else 0; mc = max(mc, cur)
exp_max = math.log(n)/math.log(1/base) if base > 0 else 0
print(f"\n=== 4. max consecutive losses ===")
print(f"  observed max streak = {mc} | i.i.d. expected ~{exp_max:.1f}  ({'longer=clustered' if mc>exp_max+1.5 else 'consistent with i.i.d.'})")
print("\nVERDICT: if (1) lift>5pp AND (3) hot-streak predicts AND (2/4) clustered -> the drawdown is a "
      "PERSISTENT regime -> a 'pause after K recent losses' circuit breaker is the actionable indicator. "
      "If all ~i.i.d. -> drawdown = variance + the 20sh air-pocket asymmetry, nothing to filter.")
