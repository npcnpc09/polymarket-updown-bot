"""bt_breaker_signal_quality.py — which rolling-loss signal better predicts the NEXT fill being a loss:
OWN (z-maker only) or COMBINED (taker+zmaker)? Uses ALL ~135 real losses (more power than the 4 cell
losses). For each fill in the combined chronological stream, compute own_roll (prior 10 zmaker losses)
and comb_roll (prior 10 combined losses), then P(this fill is a loss | roll>=2) vs base. Higher lift =
better regime signal. Also restricted to CELL trades (the ones actually downsized)."""
import json, re
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
zm = []
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None:
        m = re.search(r"-5m-(\d+)", o.get("slug", ""))
        if m: zm.append({"ws": int(m.group(1)), "won": bool(o["won"]), "sh": int(o.get("sh", 5)), "eng": "zmk"})
tk = []
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl", encoding="utf-8") if l.strip()):
    if o.get("kind") == "entry" and o.get("won") is not None:
        m = re.search(r"-5m-(\d+)", o.get("slug", ""))
        if m: tk.append({"ws": int(m.group(1)), "won": bool(o["won"]), "sh": 5, "eng": "tk"})
comb = sorted(zm+tk, key=lambda x: x["ws"])
zm.sort(key=lambda x: x["ws"])
# precompute z-maker prefix for own-roll lookup by ws
def own_roll_before(ws):
    prior = [f for f in zm if f["ws"] < ws][-10:]
    return sum(1 for f in prior if not f["won"])
n = len(comb); base = sum(1 for f in comb if not f["won"])/n*100
print(f"combined stream: {n} fills, base loss-rate {base:.1f}%\n")
# for each combined fill, own_roll & comb_roll computed from PRIOR fills
recs = []
for i, f in enumerate(comb):
    cr = sum(1 for g in comb[max(0, i-10):i] if not g["won"])
    orr = own_roll_before(f["ws"])
    recs.append((orr, cr, (not f["won"]), f["eng"], f["sh"]))
def lift(pred, lab, subset=None):
    rows = recs if subset is None else [r for r in recs if subset(r)]
    hot = [r for r in rows if pred(r)]; cool = [r for r in rows if not pred(r)]
    if not hot or not cool: print(f"  {lab}: n/a"); return
    hl = sum(1 for r in hot if r[2])/len(hot)*100; cl = sum(1 for r in cool if r[2])/len(cool)*100
    print(f"  {lab:34s} hot(n={len(hot):4d}) loss%={hl:5.1f} | cool(n={len(cool):4d}) loss%={cl:5.1f} | LIFT={hl-cl:+5.1f}pp")
print("=== predict NEXT fill = loss (ALL fills, ~135 losses) ===")
lift(lambda r: r[0] >= 2, "OWN roll>=2")
lift(lambda r: r[1] >= 2, "COMBINED roll>=2")
print("\n=== predict NEXT fill = loss, CELL trades only (sh==20) ===")
lift(lambda r: r[0] >= 2, "OWN roll>=2  (cell)", subset=lambda r: r[4] == 20)
lift(lambda r: r[1] >= 2, "COMBINED roll>=2 (cell)", subset=lambda r: r[4] == 20)
print("\nREAD: bigger positive LIFT = better regime signal (the rolling state actually flags loss-prone")
print("fills). Compare OWN vs COMBINED; the one with bigger lift (esp on CELL) is the better breaker input.")
