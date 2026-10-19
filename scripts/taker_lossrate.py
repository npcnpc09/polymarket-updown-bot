"""taker_lossrate.py — taker loss rate today / last 24h / 48h / lifetime, vs the cell maker, + by entry price.
Why is the taker's loss rate higher than the cell? It enters EARLY/CHEAP/lower-conviction (|lead|>=8 ~0.78-0.85)
vs the late z>=2.5 cell (~0.93). Lower conviction + earlier = more whipsaw, esp. in a choppy regime."""
import json
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
now=1781871880
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
tk=[]
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8") if l.strip()):
    if o.get("kind")=="entry" and o.get("won") is not None:
        w=ws_of(o.get("slug",""))
        if w: tk.append({"ws":w,"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),"paid":o.get("paid"),"coin":o.get("coin")})
tk.sort(key=lambda x:x["ws"])
def rep(s,lab):
    if not s: print(f"  {lab:18s} n=0"); return
    l=sum(1 for r in s if not r["won"]); p=sum(r["pnl"] for r in s)
    print(f"  {lab:18s} n={len(s):3d} LOSS%={l/len(s)*100:5.1f} (win%={100-l/len(s)*100:4.1f}) PnL=${p:+7.2f}")
print("=== TAKER loss rate by period ===")
rep([r for r in tk if r["ws"]>=now-86400],"last 24h")
rep([r for r in tk if r["ws"]>=now-2*86400],"last 48h")
rep([r for r in tk if r["ws"]>=now-7*86400],"last 7d")
rep(tk,"lifetime")
print("\n=== taker by entry price (is the loss in the cheap/early band?) ===")
hp=[r for r in tk if r["paid"] is not None]
rep([r for r in hp if r["paid"]<0.80],"paid <0.80 (cheap)")
rep([r for r in hp if 0.80<=r["paid"]<0.85],"paid 0.80-0.85")
rep([r for r in hp if r["paid"]>=0.85],"paid >=0.85")
print("\n=== taker last 24h by coin ===")
r24=[r for r in tk if r["ws"]>=now-86400]
for c in sorted(set(r["coin"] for r in r24)):
    rep([r for r in r24 if r["coin"]==c],c)
print("\nNOTE: taker enters EARLY at ~0.78-0.85 (lower conviction than the 0.93 cell) -> structurally lower")
print("win rate (~82% baseline vs cell ~96%); in a choppy regime the early/cheap entry whipsaws more.")
