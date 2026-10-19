"""wallet_trend.py — daily wallet (min/max/last) to see the plateau + net drift over the last ~12 days."""
import json
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
wl=[json.loads(l) for l in open(ROOT+"/data/wallet_log.jsonl",encoding="utf-8") if l.strip()]
wl.sort(key=lambda x:x["ts"])
days={}
for w in wl:
    d=datetime.fromtimestamp(w["ts"],timezone.utc).strftime("%m-%d")
    days.setdefault(d,[]).append(w["total"])
ds=sorted(days)[-13:]
print(f"{'day':6s} {'open':>7s} {'low':>7s} {'high':>7s} {'close':>7s} {'range':>6s}")
prev=None
for d in ds:
    v=days[d]; o,c,lo,hi=v[0],v[-1],min(v),max(v)
    print(f"{d:6s} {o:7.0f} {lo:7.0f} {hi:7.0f} {c:7.0f} {hi-lo:6.0f}")
first=days[ds[0]][0]; last=days[ds[-1]][-1]
print(f"\n{ds[0]} open ${first:.0f} -> {ds[-1]} now ${last:.0f}  net ${last-first:+.0f} over {len(ds)} days (${(last-first)/len(ds):+.1f}/day)")
allv=[w["total"] for w in wl if datetime.fromtimestamp(w["ts"],timezone.utc).strftime("%m-%d") in ds]
print(f"range over period: ${min(allv):.0f} - ${max(allv):.0f}  (oscillation band ${max(allv)-min(allv):.0f})")
