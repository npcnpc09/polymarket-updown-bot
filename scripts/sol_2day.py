"""sol_2day.py — SOL maker live performance, last 2 days + lifetime. Win%, PnL, by day, recent fills."""
import json
from datetime import datetime, timezone, timedelta
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
rows=[]
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_sol_live.jsonl",encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None:
        w=ws_of(o.get("slug",""))
        if w: rows.append({"ws":w,"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),"B":o.get("B"),
                           "sh":o.get("sh"),"vol":o.get("vol30"),"side":o.get("side")})
rows.sort(key=lambda x:x["ws"])
def t(ws): return datetime.fromtimestamp(ws,timezone.utc).strftime("%m-%d %H:%M")
def stat(s,lab):
    if not s: print(f"  {lab:14s} n=0"); return
    w=sum(1 for r in s if r["won"]); p=sum(r["pnl"] for r in s)
    print(f"  {lab:14s} n={len(s):3d} win%={w/len(s)*100:5.1f} PnL=${p:+7.2f}")
maxws=rows[-1]["ws"]; cut2=maxws-2*86400
print(f"=== SOL maker LIFETIME: {len(rows)} fills ===")
stat(rows,"all-time")
print(f"\n=== last 2 days ===")
recent=[r for r in rows if r["ws"]>=cut2]
stat(recent,"2d total")
for d in sorted(set(t(r["ws"])[:5] for r in recent)):
    stat([r for r in recent if t(r["ws"])[:5]==d],d)
print(f"\n=== recent SOL fills (last 15) ===")
print(f"  {'time':12s} {'side':5s} {'B':5s} {'sh':3s} {'vol':5s} {'won':5s} {'pnl':7s}")
for r in rows[-15:]:
    print(f"  {t(r['ws']):12s} {str(r['side']):5s} {str(r['B']):5s} {str(r['sh']):>3s} {str(r['vol']):5s} {str(r['won']):5s} ${r['pnl']:.2f}")
losses=[r for r in recent if not r["won"]]
print(f"\n2d losses: {len(losses)}  (${sum(r['pnl'] for r in losses):+.2f})")
