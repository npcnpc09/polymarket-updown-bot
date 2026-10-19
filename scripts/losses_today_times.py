"""losses_today_times.py — every loss TODAY (UTC) with UTC and UTC+8 (China) clock times."""
import json
from datetime import datetime, timezone, timedelta
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
                if w: allf.append({"eng":name,"ws":w,"coin":o.get("coin"),"side":o.get("side"),"won":bool(o["won"]),
                                   "pnl":float(o.get("pnl",0) or 0),"B":o.get("B"),"sh":o.get("sh"),"roll10":o.get("roll10"),"brk":o.get("breaker")})
    except FileNotFoundError: pass
allf.sort(key=lambda x:x["ws"])
today=datetime.fromtimestamp(allf[-1]["ws"],timezone.utc).strftime("%Y-%m-%d")
cn=timezone(timedelta(hours=8))
losses=[r for r in allf if not r["won"] and datetime.fromtimestamp(r["ws"],timezone.utc).strftime("%Y-%m-%d")==today]
print(f"=== losses today {today} (UTC) — {len(losses)} ===")
print(f"{'UTC':6s} {'CN+8':6s} {'eng':9s} {'coin':4s} {'side':5s} {'B':5s} {'sh':3s} {'pnl':7s} roll10/brk")
for r in losses:
    u=datetime.fromtimestamp(r["ws"],timezone.utc).strftime("%H:%M")
    c=datetime.fromtimestamp(r["ws"],cn).strftime("%H:%M")
    print(f"{u:6s} {c:6s} {r['eng']:9s} {str(r['coin']):4s} {str(r['side']):5s} {str(r['B']):5s} {str(r['sh']):3s} ${r['pnl']:+.2f}  {r.get('roll10')}/{r.get('brk')}")
