"""today_pnl.py — wins/losses + PnL TODAY (UTC) across ALL live engines, per engine and combined."""
import json
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(slug):
    try: return int(slug.rsplit("-",1)[1])
    except: return None
srcs = [
 ("data/multi_window_engine_live.jsonl","zmaker5m", lambda o: o.get("filled") is True and o.get("won") is not None),
 ("data/multi_window_engine_15m_live.jsonl","15m", lambda o: o.get("filled") is True and o.get("won") is not None),
 ("data/multi_window_engine_sol_live.jsonl","sol", lambda o: o.get("filled") is True and o.get("won") is not None),
 ("data/early_taker_probe.jsonl","taker", lambda o: o.get("kind")=="entry" and o.get("won") is not None),
]
allf=[]
for f,name,keep in srcs:
    try:
        for o in (json.loads(l) for l in open(ROOT+"/"+f, encoding="utf-8") if l.strip()):
            if keep(o):
                w=ws_of(o.get("slug",""))
                if w: allf.append({"eng":name,"ws":w,"coin":o.get("coin"),"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0)})
    except FileNotFoundError: pass
allf.sort(key=lambda x:x["ws"])
today = datetime.fromtimestamp(allf[-1]["ws"],timezone.utc).strftime("%Y-%m-%d")
td=[r for r in allf if datetime.fromtimestamp(r["ws"],timezone.utc).strftime("%Y-%m-%d")==today]
def line(s,lab):
    if not s: return
    w=sum(1 for r in s if r["won"]); l=len(s)-w; p=sum(r["pnl"] for r in s)
    wp=sum(r["pnl"] for r in s if r["won"]); lp=sum(r["pnl"] for r in s if not r["won"])
    print(f"  {lab:12s} fills={len(s):3d}  WON {w:3d} (+${wp:6.2f})  LOST {l:3d} (${lp:7.2f})  NET ${p:+7.2f}")
print(f"=== TODAY {today} (UTC) — all live engines ===")
line(td,"ALL")
print("  --- per engine ---")
for name in ("zmaker5m","taker","15m","sol"):
    line([r for r in td if r["eng"]==name],name)
print("  --- per coin ---")
for c in sorted(set(r["coin"] for r in td)):
    line([r for r in td if r["coin"]==c],str(c))
