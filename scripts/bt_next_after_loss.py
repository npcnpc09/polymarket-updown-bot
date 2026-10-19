"""bt_next_after_loss.py — enumerate: after each loss (and each 20sh CELL air-pocket), was the IMMEDIATELY
NEXT trade (time-ordered combined stream) also a loss? Lists the concrete cases + summary."""
import json, re
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
F = []
def add(f, eng):
    for o in (json.loads(l) for l in open(ROOT+"/"+f, encoding="utf-8") if l.strip()):
        ok = (o.get("kind") == "entry") or (o.get("filled") is True)
        if ok and o.get("won") is not None and o.get("pnl") is not None:
            m = re.search(r"(btc|eth|sol)-updown-5m-(\d+)", o.get("slug", ""))
            if m: F.append({"ws": int(m.group(2)), "coin": m.group(1), "won": bool(o["won"]),
                            "pnl": float(o.get("pnl", 0)), "sh": int(o.get("sh", 5)), "eng": eng})
add("data/early_taker_probe.jsonl", "taker"); add("data/multi_window_engine_live.jsonl", "zmk"); add("data/multi_window_engine_sol_live.jsonl", "sol")
F.sort(key=lambda x: x["ws"])
n = len(F)
def t(x): return datetime.fromtimestamp(x["ws"], timezone.utc).strftime("%m-%d %H:%M")

losses = [i for i in range(n) if not F[i]["won"]]
print(f"{n} time-ordered fills, {len(losses)} losses\n")

# next-after-each-loss
nextloss = 0; counted = 0
print("=== every loss -> was the NEXT trade also a loss? ===")
for i in losses:
    if i+1 < n:
        counted += 1
        nx = F[i+1]; gap = (nx["ws"]-F[i]["ws"])/60
        if not nx["won"]: nextloss += 1
        # only print the cell air-pockets + cases where next was also a loss (to keep it readable)
        cur = F[i]
        if cur["sh"] == 20 or (not nx["won"]):
            tag = "AIRPOCKET(20sh)" if cur["sh"] == 20 else "loss"
            res = ("-> NEXT ALSO LOSS" if not nx["won"] else "-> next WON")
            print(f"  {t(cur)} {cur['eng']} {cur['coin']} {tag} ${cur['pnl']}  |  +{gap:.0f}min next={nx['eng']} {nx['coin']} {'LOSS $'+str(nx['pnl']) if not nx['won'] else 'win'}  {res}")
print(f"\n  SUMMARY: of {counted} losses, {nextloss} were immediately followed by another loss = {nextloss/counted*100:.1f}% (baseline loss-rate {len(losses)/n*100:.1f}%)")

# the 3 cell air-pockets specifically, with next 3 trades
print("\n=== the 20sh CELL air-pockets, with the next 3 trades each ===")
for i in losses:
    if F[i]["sh"] == 20:
        print(f"  {t(F[i])} {F[i]['coin']} CELL ${F[i]['pnl']}:")
        for j in range(i+1, min(i+4, n)):
            print(f"      +{(F[j]['ws']-F[i]['ws'])/60:.0f}min {F[j]['eng']} {F[j]['coin']} sh{F[j]['sh']} {'LOSS $'+str(F[j]['pnl']) if not F[j]['won'] else 'WON'}")
