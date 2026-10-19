"""bt_btc_only_cell.py — (1) held-out stability: is eth-cell worse than btc-cell in BOTH train & held-out?
(2) policy impact: cell upsize (20/28) for BTC only, eth cell -> 5sh. Recompute total cell PnL/G + the
air-pocket variance reduction. Sizing is a counterfactual multiplier on real won/B."""
import json
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
cells=[]
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl",encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None and o.get("B") and 0.90<=o["B"]<0.96 and o.get("coin") in ("btc","eth"):
        w=ws_of(o.get("slug",""))
        if w: cells.append({"ws":w,"coin":o["coin"],"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),
                            "sh":int(o.get("sh",5)),"B":float(o["B"])})
cells.sort(key=lambda x:x["ws"])
def stats(s):
    if not s: return (0,0,0,0)
    n=len(s); loss=sum(1 for r in s if not r["won"])/n*100
    pnl=sum(r["pnl"] for r in s); risk=sum(r["sh"]*r["B"] for r in s)
    return n,loss,pnl,(pnl/risk*100 if risk else 0)
def show(s,lab):
    n,l,p,g=stats(s); print(f"  {lab:18s} n={n:3d} loss%={l:4.1f} PnL=${p:+8.2f} G={g:+.2f}%")
print("=== (1) held-out stability: eth-cell vs btc-cell ===")
cut=cells[int(len(cells)*0.6)]["ws"]
for nm,sub in (("TRAIN(first60%)",[c for c in cells if c["ws"]<cut]),("HELD-OUT(last40%)",[c for c in cells if c["ws"]>=cut])):
    print(f" {nm}:")
    show([c for c in sub if c["coin"]=="btc"],"btc cell")
    show([c for c in sub if c["coin"]=="eth"],"eth cell")
# (2) policy: btc-only upsize; eth cell -> 5sh
def pnl5(c): return 5*(1-c["B"]) if c["won"] else -5*c["B"]
cur_pnl=sum(c["pnl"] for c in cells); cur_risk=sum(c["sh"]*c["B"] for c in cells)
new_pnl=sum(c["pnl"] if c["coin"]=="btc" else pnl5(c) for c in cells)
new_risk=sum((c["sh"] if c["coin"]=="btc" else 5)*c["B"] for c in cells)
print("\n=== (2) policy impact: CURRENT (both upsize) vs BTC-ONLY upsize (eth cell->5sh) ===")
print(f"  CURRENT     total cell PnL=${cur_pnl:+8.2f}  risk=${cur_risk:7.0f}  G={cur_pnl/cur_risk*100:+.2f}%")
print(f"  BTC-ONLY    total cell PnL=${new_pnl:+8.2f}  risk=${new_risk:7.0f}  G={new_pnl/new_risk*100:+.2f}%")
print(f"  delta PnL = ${new_pnl-cur_pnl:+.2f} (what eth-cell upsize contributed: ${cur_pnl-new_pnl:+.2f})")
# eth cell air-pockets (20sh+ losses) reduction
ap=[c for c in cells if c["coin"]=="eth" and c["sh"]>=20 and not c["won"]]
print(f"\n  eth-cell air-pockets (>=20sh losses): {len(ap)}, total ${sum(c['pnl'] for c in ap):+.2f}")
print(f"    -> at 5sh they'd be ${sum(pnl5(c) for c in ap):+.2f} (variance saved ${sum(c['pnl'] for c in ap)-sum(pnl5(c) for c in ap):+.2f})")
ape=[c for c in cells if c["coin"]=="eth" and c["sh"]>=20]
if ape:
    print(f"  eth-cell upsized (>=20sh) fills: {len(ape)}, win%={sum(1 for c in ape if c['won'])/len(ape)*100:.1f}, net at 20-28sh=${sum(c['pnl'] for c in ape):+.2f} vs at 5sh=${sum(pnl5(c) for c in ape):+.2f}")
print("\nREAD: deploy btc-only-cell iff eth-cell is worse in BOTH halves AND btc-only G >= current G (eth-cell")
print("upsize was ~breakeven so dropping it should barely cost PnL while cutting air-pocket variance).")
