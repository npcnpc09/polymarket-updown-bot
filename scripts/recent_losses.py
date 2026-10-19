"""recent_losses.py — list the most recent REAL losses across active live engines, by coin."""
import json
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
from datetime import datetime, timezone
def ws_of(slug):
    try: return int(slug.rsplit("-",1)[1])
    except: return None
def t(ws): return datetime.fromtimestamp(ws,timezone.utc).strftime("%m-%d %H:%M") if ws else "?"

srcs = [
 ("data/multi_window_engine_live.jsonl", "zmaker5m", lambda o: o.get("filled") is True and o.get("won") is not None),
 ("data/multi_window_engine_15m_live.jsonl", "zmaker15m", lambda o: o.get("filled") is True and o.get("won") is not None),
 ("data/multi_window_engine_sol_live.jsonl", "solmaker", lambda o: o.get("filled") is True and o.get("won") is not None),
 ("data/early_taker_probe.jsonl", "taker5m", lambda o: o.get("kind")=="entry" and o.get("won") is not None),
]
allf = []
for f, name, keep in srcs:
    try:
        for o in (json.loads(l) for l in open(ROOT+"/"+f, encoding="utf-8") if l.strip()):
            if keep(o):
                ws = ws_of(o.get("slug",""))
                allf.append({"eng":name,"ws":ws,"coin":o.get("coin"),"side":o.get("side"),
                             "B":o.get("B"),"sh":o.get("sh"),"won":bool(o["won"]),
                             "pnl":float(o.get("pnl",0) or 0),"vol":o.get("vol30"),"z":o.get("zscore")})
    except FileNotFoundError: pass
allf = [x for x in allf if x["ws"]]
allf.sort(key=lambda x:x["ws"])
losses = [x for x in allf if not x["won"]]
print(f"=== last 20 REAL losses (all live engines), most recent last ===")
print(f"{'time':12s} {'eng':10s} {'coin':4s} {'side':5s} {'B':5s} {'sh':3s} {'pnl':7s} {'vol':5s} {'z':4s}")
for x in losses[-20:]:
    print(f"{t(x['ws']):12s} {x['eng']:10s} {str(x['coin']):4s} {str(x['side']):5s} {str(x['B']):5s} {str(x['sh']):3s} {x['pnl']:6.2f} {str(round(x['vol'],1) if x['vol'] else '-'):5s} {str(x['z']):4s}")
print(f"\n=== loss count + $ by coin (last 7 days of fills) ===")
import collections
cut = (allf[-1]["ws"] - 7*86400) if allf else 0
recent = [x for x in allf if x["ws"]>=cut]
byc = collections.defaultdict(lambda:[0,0,0.0,0.0])  # n, nloss, losspnl, totpnl
for x in recent:
    byc[x["coin"]][0]+=1
    byc[x["coin"]][3]+=x["pnl"]
    if not x["won"]: byc[x["coin"]][1]+=1; byc[x["coin"]][2]+=x["pnl"]
for c,(n,nl,lp,tp) in sorted(byc.items(), key=lambda kv:kv[1][2]):
    print(f"  {str(c):4s} fills={n:3d} losses={nl:3d} ({nl/n*100:4.0f}%) loss$={lp:+7.2f} net$={tp:+7.2f}")
print(f"\n=== loss $ by engine x coin (last 7d) ===")
bye = collections.defaultdict(float)
for x in recent:
    if not x["won"]: bye[(x["eng"],x["coin"])]+=x["pnl"]
for (e,c),p in sorted(bye.items(), key=lambda kv:kv[1]):
    print(f"  {e:10s} {str(c):4s} loss$={p:+7.2f}")
