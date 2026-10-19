"""On early_taker's REAL fills, what would different PRICE CAPS net? The winner analysis said <0.65 is the only
+EV cell and early_taker (cap 0.85) keeps taking 0.80/0.81 expensive ones. Filter real trades to paid<cap and
compute real net PnL/win%/EV per cap. Shows whether tightening the cap (the one variant dimension that maps to
the +EV cheap zone) actually improves early_taker on its own real data."""
import json,os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows=[json.loads(l) for l in open(os.path.join(ROOT,"data","early_taker_probe.jsonl"),encoding="utf-8") if l.strip()]
T=[r for r in rows if r.get("live") and r.get("kind")=="entry" and r.get("paid") is not None and "won" in r]
print("early_taker real fills: %d\n"%len(T))
print("%-8s %5s %5s %10s %9s"%("cap","n","win%","netPnL$","EV/sh"))
for cap in (0.86,0.80,0.75,0.70,0.65,0.60):
    g=[r for r in T if r["paid"]<cap]
    if not g: continue
    n=len(g); w=sum(1 for r in g if r["won"])
    pnl=sum(((1-r["paid"]) if r["won"] else -r["paid"])*5 for r in g)
    print("<%.2f    %5d %4.0f%% %+9.2f %+8.3f"%(cap,n,w/n*100,pnl,pnl/(5*n)))
print("\n(5 shares/trade; netPnL = real settled PnL of all fills under that cap)")
# also: the expensive slice that a 0.70 cap would have SKIPPED
exp=[r for r in T if r["paid"]>=0.70]
if exp:
    epnl=sum(((1-r["paid"]) if r["won"] else -r["paid"])*5 for r in exp)
    print("paid>=0.70 slice (what a 0.70-cap skips): n=%d win%.0f%% PnL$%+.2f"%(len(exp),sum(1 for r in exp if r["won"])/len(exp)*100,epnl))
