"""cell_today.py — every CELL entry (B in 0.90-0.95) on the live 5m z-maker TODAY (UTC): share size + tier."""
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
                           "breaker":o.get("breaker"),"deepcalm":o.get("deepcalm")})
rows.sort(key=lambda x:x["ws"])
today=datetime.fromtimestamp(rows[-1]["ws"],timezone.utc).strftime("%Y-%m-%d")
cell=[r for r in rows if r["B"] is not None and 0.90<=r["B"]<0.96
      and datetime.fromtimestamp(r["ws"],timezone.utc).strftime("%Y-%m-%d")==today]
print(f"=== CELL entries TODAY {today} (UTC): {len(cell)} ===")
print(f"{'time':6s} {'coin':4s} {'side':5s} {'B':5s} {'sh':3s} {'tier':9s} {'won':5s} {'pnl':7s}")
from collections import Counter
szc=Counter()
for r in cell:
    t=datetime.fromtimestamp(r["ws"],timezone.utc).strftime("%H:%M")
    tier="breaker5" if r.get("breaker") else ("deepcalm28" if r.get("deepcalm") else "normal20")
    szc[r["sh"]]+=1
    print(f"{t:6s} {r['coin']:4s} {r['side']:5s} {str(r['B']):5s} {r['sh']:<3d} {tier:9s} {str(r['won']):5s} ${r['pnl']:+.2f}")
w=sum(1 for r in cell if r["won"]); p=sum(r["pnl"] for r in cell)
print(f"\ncell totals: {len(cell)} fills, WON {w}/{len(cell)}, PnL ${p:+.2f}")
print("share-size breakdown:", dict(sorted(szc.items())))
