"""zmaker_today.py — how did the live z-maker (5m, PID 8320 --combined) do TODAY (UTC)?
Win%, PnL, cell vs non-cell, breaker/deepcalm activity. Today = same UTC date as the latest fill."""
import json
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(slug):
    try: return int(slug.rsplit("-",1)[1])
    except: return None
rows=[]
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None:
        w=ws_of(o.get("slug",""))
        if w: rows.append({"ws":w,"coin":o.get("coin"),"side":o.get("side"),"won":bool(o["won"]),
                           "pnl":float(o.get("pnl",0) or 0),"B":o.get("B"),"sh":int(o.get("sh",5)),
                           "roll10":o.get("roll10"),"breaker":o.get("breaker"),"deepcalm":o.get("deepcalm"),"in_cell":o.get("in_cell")})
rows.sort(key=lambda x:x["ws"])
if not rows: print("no fills"); raise SystemExit
today = datetime.fromtimestamp(rows[-1]["ws"],timezone.utc).strftime("%Y-%m-%d")
td=[r for r in rows if datetime.fromtimestamp(r["ws"],timezone.utc).strftime("%Y-%m-%d")==today]
def stat(s,lab):
    if not s: print(f"  {lab:22s} n=0"); return
    w=sum(1 for r in s if r["won"]); p=sum(r["pnl"] for r in s)
    print(f"  {lab:22s} n={len(s):3d} win%={w/len(s)*100:5.1f} PnL=${p:+7.2f}")
print(f"=== z-maker TODAY ({today} UTC): {len(td)} fills ===")
stat(td,"ALL")
stat([r for r in td if r["coin"]=="btc"],"btc")
stat([r for r in td if r["coin"]=="eth"],"eth")
print("  --- by band ---")
stat([r for r in td if r["B"] is not None and 0.90<=r["B"]<0.96],"cell 0.90-0.95")
stat([r for r in td if r["B"] is not None and r["B"]<0.90],"non-cell <0.90")
print("  --- by size (cell sizing / breaker) ---")
stat([r for r in td if r["sh"]>=20],"20sh+ (cell full/calm)")
stat([r for r in td if r["sh"]==5],"5sh (base/breaker-down)")
brk=[r for r in td if r.get("breaker")]; dc=[r for r in td if r.get("deepcalm")]
print(f"  breaker-fired fills: {len(brk)} | deepcalm fills: {len(dc)}")
if brk: stat(brk,"  breaker-downsized")
losses=[r for r in td if not r["won"]]
print(f"\n  losses today: {len(losses)}")
for r in losses:
    t=datetime.fromtimestamp(r["ws"],timezone.utc).strftime("%H:%M")
    print(f"    {t} {r['coin']} {r['side']} B={r['B']} sh={r['sh']} ${r['pnl']:.2f} roll10={r.get('roll10')}")
# session-to-date cumulative for context
allp=sum(r["pnl"] for r in rows)
print(f"\n  z-maker file lifetime: {len(rows)} fills, win% {sum(1 for r in rows if r['won'])/len(rows)*100:.1f}, PnL ${allp:+.2f}")
