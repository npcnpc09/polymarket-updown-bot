"""pnl_15m.py — lifetime PnL of the 15m engine (settled fills only)."""
import json, time
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
rows=[]
for l in open(ROOT+"/data/multi_window_engine_15m_live.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    try: o=json.loads(l)
    except: continue
    if o.get("filled") is True and o.get("won") is not None:
        rows.append(o)
if not rows:
    print("no settled 15m fills yet"); raise SystemExit
rows.sort(key=lambda o:o.get("ws") or int(o["slug"].rsplit("-",1)[1]))
def ws(o): return o.get("ws") or int(o["slug"].rsplit("-",1)[1])
n=len(rows); wins=sum(1 for o in rows if o["won"])
pnl=sum(float(o.get("pnl",0) or 0) for o in rows)
risk=sum(float(o.get("sh",5) or 5)*float(o.get("B") or 0.8) for o in rows)
first,last=ws(rows[0]),ws(rows[-1])
print("=== 15m engine — lifetime (settled fills) ===")
print(f"  fills      : {n}")
print(f"  win%       : {wins/n*100:.1f}  ({wins}W / {n-wins}L)")
print(f"  PnL        : ${pnl:+.2f}")
print(f"  G (pnl/risk): {pnl/risk*100:+.2f}%   (risk deployed ${risk:.0f})")
span=(last-first)/86400
print(f"  span       : {span:.1f} days  (first ws {first} -> last {last})")
print("  --- by coin ---")
for c in ("btc","eth"):
    cr=[o for o in rows if o.get("coin")==c]
    if cr:
        w=sum(1 for o in cr if o["won"]); p=sum(float(o.get("pnl",0) or 0) for o in cr)
        print(f"    {c}: n={len(cr):3d} win%={w/len(cr)*100:5.1f} PnL=${p:+7.2f}")
# running cumulative + peak/trough
cum=0; peak=0; trough=0; mx=-1e9; mn=1e9
for o in rows:
    cum+=float(o.get("pnl",0) or 0); mx=max(mx,cum); mn=min(mn,cum)
print(f"  --- arc ---  peak cum ${mx:+.2f} / trough cum ${mn:+.2f} / final ${cum:+.2f}")
# last 10
print("  --- last 10 settled ---")
for o in rows[-10:]:
    print(f"    {o.get('coin')} {'W' if o['won'] else 'L'} pnl={float(o.get('pnl',0) or 0):+.2f} B={o.get('B')} sh={o.get('sh')}")
