"""zmaker_loss_vol.py — are the recent z-maker losses in HIGHER-vol periods than the wins? Pull vol30/zscore
/lead at entry for recent z-maker losses vs wins (and cell-band specifically). Tests the user's high-vol read
against the logged data. NOTE prior: cell air-pocket was hypothesized LOW-vol z-inflation, and losses tested
vol-INDEPENDENT — so check, don't assume."""
import json
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
rows=[]
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl",encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None:
        w=ws_of(o.get("slug",""))
        if w: rows.append({"ws":w,"coin":o.get("coin"),"side":o.get("side"),"won":bool(o["won"]),
                           "pnl":float(o.get("pnl",0) or 0),"B":o.get("B"),"sh":o.get("sh"),
                           "vol":o.get("vol30"),"z":o.get("zscore"),"lead":o.get("lead")})
rows.sort(key=lambda x:x["ws"])
def t(ws): return datetime.fromtimestamp(ws,timezone.utc).strftime("%m-%d %H:%M")
import statistics as st
def vols(s): return [r["vol"] for r in s if r["vol"] is not None]
def line(s,lab):
    v=vols(s)
    if not v: print(f"  {lab:24s} n=0"); return
    print(f"  {lab:24s} n={len(s):3d}  vol30 med={st.median(v):4.1f} mean={st.mean(v):4.1f} min={min(v):4.1f} max={max(v):4.1f}")
print("=== z-maker: vol30 distribution, WINS vs LOSSES (all logged) ===")
W=[r for r in rows if r["won"]]; L=[r for r in rows if not r["won"]]
line(W,"WINS"); line(L,"LOSSES")
print("\n=== cell-band (0.90-0.95) only ===")
cw=[r for r in rows if r["B"] and 0.90<=r["B"]<0.96 and r["won"]]
clo=[r for r in rows if r["B"] and 0.90<=r["B"]<0.96 and not r["won"]]
line(cw,"cell WINS"); line(clo,"cell LOSSES")
print("\n=== the recent z-maker LOSSES (last 12), with vol/z/lead ===")
print(f"  {'time':12s} {'coin':4s} {'side':5s} {'B':5s} {'sh':3s} {'vol':5s} {'z':5s} {'lead':6s} {'pnl':7s}")
for r in L[-12:]:
    print(f"  {t(r['ws']):12s} {str(r['coin']):4s} {str(r['side']):5s} {str(r['B']):5s} {str(r['sh']):>3s} {str(r['vol']):5s} {str(r['z']):5s} {str(r['lead']):6s} ${r['pnl']:.2f}")
print("\nREAD: claim holds only if LOSS vol30 median is clearly ABOVE win vol30 median. If similar/below,")
print("the losses are NOT a high-vol phenomenon (matches prior: cell losses vol-independent / low-vol-z-inflation).")
