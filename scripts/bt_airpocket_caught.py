"""bt_airpocket_caught.py — for each REAL cell air-pocket (zmaker sh=20 loss), would the COMBINED breaker
have downsized it (combined rolling-10 >=2 at that moment) -> -$18.8 becomes -$4.65? Compare vs OWN."""
import json, re
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(slug):
    try: return int(slug.rsplit("-", 1)[1])
    except: return None
zm = []
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None:
        w = ws_of(o.get("slug", ""))
        if w: zm.append({"ws": w, "won": bool(o["won"]), "sh": int(o.get("sh", 5)), "pnl": float(o.get("pnl", 0)), "coin": o.get("coin"), "side": o.get("side"), "B": o.get("B")})
tk = []
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl", encoding="utf-8") if l.strip()):
    if o.get("kind") == "entry" and o.get("won") is not None:
        w = ws_of(o.get("slug", ""))
        if w: tk.append({"ws": w, "won": bool(o["won"])})
zm.sort(key=lambda x: x["ws"]); comb = sorted([{"ws": f["ws"], "won": f["won"]} for f in zm]+tk, key=lambda x: x["ws"])
from datetime import datetime, timezone
# own/comb rolling just BEFORE a given ws
def roll(stream, ws):
    prior = [f for f in stream if f["ws"] < ws][-10:]
    return sum(1 for f in prior if not f["won"]), len(prior)
airpockets = [f for f in zm if f["sh"] == 20 and not f["won"]]
print(f"=== cell air-pockets (zmaker 20sh losses): {len(airpockets)} ===")
print(f"{'time':16s} {'coin':4s} {'side':5s} {'B':5s} {'pnl':7s} | {'OWN roll':>9s} | {'COMB roll':>10s} | combined verdict")
caught_c = 0; caught_o = 0
for a in airpockets:
    t = datetime.fromtimestamp(a["ws"], timezone.utc).strftime("%m-%d %H:%M")
    orr, on = roll(zm, a["ws"]); cr, cn = roll(comb, a["ws"])
    oc = orr >= 2; cc = cr >= 2
    if cc: caught_c += 1
    if oc: caught_o += 1
    print(f"{t:16s} {a['coin']:4s} {a['side']:5s} {str(a['B']):5s} ${a['pnl']:6.1f} | {orr}/{on:<6} | {cr}/{cn:<7} | {'CAUGHT -> -$4.65 (saved ~$14)' if cc else 'missed -> still -$18'}")
print(f"\n  OWN breaker would have caught: {caught_o}/{len(airpockets)}")
print(f"  COMBINED breaker would have caught: {caught_c}/{len(airpockets)}")
saved = caught_c*14.0
print(f"  COMBINED would have saved ~${saved:.0f} on these air-pockets (each catch: -$18.8 -> -$4.65 = +$14)")
print("\nNOTE: 'caught' = combined rolling-10 had >=2 losses at that moment -> cell auto-downsized to 5sh.")
