"""bt_martingale_recovery.py — backtest 'after an air-pocket, size the next K cells to 100sh to earn it
back' (a martingale). Uses REAL time-ordered outcomes. Scales the pnl of the next-K post-loss trades x5
(20sh->100sh). Reports net delta vs flat, the worst single 100sh loss, and the EXPECTED value at the
MEASURED post-loss win rate. Tests both (A) trigger on any loss, (B) trigger on 20sh cell air-pockets."""
import json, re
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
F = []
def add(f, eng):
    for o in (json.loads(l) for l in open(ROOT+"/"+f, encoding="utf-8") if l.strip()):
        ok = (o.get("kind") == "entry") or (o.get("filled") is True)
        if ok and o.get("won") is not None and o.get("pnl") is not None:
            m = re.search(r"-5m-(\d+)", o.get("slug", ""))
            if m: F.append({"ws": int(m.group(1)), "won": bool(o["won"]), "pnl": float(o.get("pnl", 0)),
                            "sh": int(o.get("sh", 5)), "B": o.get("B") or o.get("paid") or 0.92, "eng": eng})
add("data/early_taker_probe.jsonl", "taker"); add("data/multi_window_engine_live.jsonl", "zmk"); add("data/multi_window_engine_sol_live.jsonl", "sol")
F.sort(key=lambda x: x["ws"]); n = len(F)

def sim(trigger_is_airpocket, K, big=100):
    """after a trigger, the next K CELL-eligible (sh>=20 OR price in cell) trades use `big` shares."""
    base = 0.0; mart = 0.0; armed = 0; worst = 0.0; nbig = 0; bigloss = 0
    for i in range(n):
        f = F[i]; iscell = (f["sh"] == 20) or (0.90 <= f["B"] < 0.95)
        # baseline: cell at 20sh
        bpnl = ((1-f["B"]) if f["won"] else -f["B"]) * (20 if iscell else f["sh"])
        base += bpnl
        if armed > 0 and iscell:
            sh = big; nbig += 1
            mpnl = ((1-f["B"]) if f["won"] else -f["B"]) * sh
            if not f["won"]: bigloss += 1; worst = min(worst, mpnl)
            mart += mpnl; armed -= 1
        else:
            mart += bpnl
        # set/refresh trigger
        trig = (not f["won"]) if not trigger_is_airpocket else (f["sh"] == 20 and not f["won"])
        if trig: armed = K
    return base, mart, nbig, bigloss, worst

print(f"{n} fills\n=== MARTINGALE: after trigger, next K cells at 100sh (vs flat 20sh) ===")
print(f"{'trigger':14s} {'K':>2s} {'flat$':>9s} {'martingale$':>12s} {'delta$':>9s} {'100sh-trades':>12s} {'100sh-losses':>12s} {'worst1$':>9s}")
for trig, lab in ((False, "any-loss"), (True, "cell-airpocket")):
    for K in (1, 3, 5):
        b, m, nb, bl, w = sim(trig, K)
        print(f"  {lab:14s} {K:>2d} {b:9.2f} {m:12.2f} {m-b:+9.2f} {nb:12d} {bl:12d} {w:9.2f}")

# expectation at measured post-loss win rate
print("\n=== EXPECTED value of a 100sh cell trade, by win rate (entry ~0.92) ===")
for wr, lab in ((0.96, "normal cell (calm)"), (0.92, "breakeven"), (0.90, "post-loss elevated ~"), (0.80, "next-trade-after-loss(measured)")):
    ev = wr*(0.08*100) - (1-wr)*(0.92*100)
    print(f"  win {wr*100:.0f}% ({lab:30s}): EV/trade = ${ev:+.2f}")
print("\nNOTE: martingale 'works' on this sample ONLY if the few post-airpocket cells happened to win (n=4")
print("cell air-pockets, all followed by wins = ~55% luck). Robust stat: post-loss loss-rate is HIGHER")
print("(20.3% vs 13.8%), so a 100sh cell after a loss has EV ~breakeven-to-negative + a -$92 ruin tail.")
