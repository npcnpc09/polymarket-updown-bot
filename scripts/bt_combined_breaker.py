"""bt_combined_breaker.py — does feeding the breaker the COMBINED (taker+zmaker) stream beat the current
z-maker-OWN stream? The breaker downsizes the CELL (zmaker sh=20 -> 5) when rolling-10 has >=2 losses.
Compare cell net PnL under: NONE / OWN-stream breaker (current) / COMBINED-stream breaker (proposed).
Key diagnostic: win% of the cell trades each breaker DOWNSIZES (low = catching losers = good; ~normal =
forgoing wins = false signal)."""
import json, re
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
zm = []  # z-maker stream
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None and o.get("pnl") is not None:
        m = re.search(r"-5m-(\d+)", o.get("slug", ""))
        if m: zm.append({"ws": int(m.group(1)), "won": bool(o["won"]), "pnl": float(o["pnl"]), "sh": int(o.get("sh", 5)), "eng": "zmk"})
tk = []
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl", encoding="utf-8") if l.strip()):
    if o.get("kind") == "entry" and o.get("won") is not None and o.get("pnl") is not None:
        m = re.search(r"-5m-(\d+)", o.get("slug", ""))
        if m: tk.append({"ws": int(m.group(1)), "won": bool(o["won"]), "pnl": float(o["pnl"]), "sh": 5, "eng": "tk"})
zm.sort(key=lambda x: x["ws"]); comb = sorted(zm+tk, key=lambda x: x["ws"])
# index of each zmaker fill within the combined stream
for i, f in enumerate(comb): f["_ci"] = i
# rolling-10 loss helpers
def roll_own(zidx): return sum(1 for f in zm[max(0, zidx-10):zidx] if not f["won"])
def roll_comb(cidx): return sum(1 for f in comb[max(0, cidx-10):cidx] if not f["won"])
# build cell list with both rolling signals
cells = []
ci = 0
for zi, f in enumerate(zm):
    # find this fill in comb (match by ws+pnl+eng) — use a pointer
    while ci < len(comb) and not (comb[ci]["eng"] == "zmk" and comb[ci]["ws"] == f["ws"] and comb[ci]["pnl"] == f["pnl"]): ci += 1
    cidx = ci; ci += 1
    if f["sh"] == 20:  # a CELL trade
        cells.append({"won": f["won"], "pnl20": f["pnl"], "r_own": roll_own(zi), "r_comb": roll_comb(cidx)})
print(f"cell trades: {len(cells)} | win%={sum(1 for c in cells if c['won'])/len(cells)*100:.1f}")
def sim(mode):
    tot = 0.0; touched = []
    for c in cells:
        down = (c["r_own"] >= 2) if mode == "own" else ((c["r_comb"] >= 2) if mode == "comb" else False)
        tot += c["pnl20"]*(5.0/20.0) if down else c["pnl20"]
        if down: touched.append(c)
    return tot, touched
for mode, lab in (("none", "NO breaker (cell always 20sh)"), ("own", "OWN-stream breaker (current)"), ("comb", "COMBINED-stream breaker (proposed)")):
    tot, t = sim(mode)
    if t:
        tw = sum(1 for c in t if c["won"])/len(t)*100
        print(f"  {lab:38s} cellPnL=${tot:+7.2f} | downsized {len(t)} cells (win%={tw:.0f}% vs base {sum(1 for c in cells if c['won'])/len(cells)*100:.0f}%)")
    else:
        print(f"  {lab:38s} cellPnL=${tot:+7.2f} | downsized 0")
print("\nREAD: the breaker helps if the cells it DOWNSIZES have a LOW win% (catching losers). If combined-")
print("stream downsizes more cells but at ~normal win% -> it's a false signal (taker losses don't predict")
print("cell losses) and it just forgoes cell wins. Best mode = highest cellPnL.")
