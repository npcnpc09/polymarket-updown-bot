"""soundness_dossier.py — is the strategy SOUND enough to scale? Real-money evidence: per-engine cumulative
PnL / win% / G / n, time-split consistency (durability, not one lucky run), and the cell as the core engine.
Honest assessment: a real but THIN edge; scaling amplifies both edge and variance."""
import json, statistics as st
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
def load(f,eng,keep):
    out=[]
    try:
        for o in (json.loads(l) for l in open(ROOT+"/"+f,encoding="utf-8") if l.strip()):
            if keep(o):
                w=ws_of(o.get("slug",""))
                if w:
                    sh=float(o.get("sh",5) or 5); B=float(o.get("B") or o.get("paid") or 0.8)
                    out.append({"eng":eng,"ws":w,"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),"risk":sh*B,"B":o.get("B"),"coin":o.get("coin")})
    except FileNotFoundError: pass
    return out
zm=load("data/multi_window_engine_live.jsonl","zmaker",lambda o:o.get("filled") is True and o.get("won") is not None)
tk=load("data/early_taker_probe.jsonl","taker",lambda o:o.get("kind")=="entry" and o.get("won") is not None)
m15=load("data/multi_window_engine_15m_live.jsonl","15m",lambda o:o.get("filled") is True and o.get("won") is not None)
sol=load("data/multi_window_engine_sol_live.jsonl","sol",lambda o:o.get("filled") is True and o.get("won") is not None)
allf=zm+tk+m15+sol
def stats(s):
    if not s: return (0,0,0,0)
    n=len(s); w=sum(1 for r in s if r["won"])/n*100; p=sum(r["pnl"] for r in s); risk=sum(r["risk"] for r in s)
    return n,w,p,(p/risk*100 if risk else 0)
def line(s,lab):
    n,w,p,g=stats(s)
    if n: print(f"  {lab:16s} n={n:4d} win%={w:5.1f} PnL=${p:+8.2f} G={g:+.2f}%")
print("=== PER-ENGINE real-money track record (lifetime) ===")
line(zm,"z-maker(all)"); line([f for f in zm if f["B"] and 0.90<=f["B"]<0.96],"  > CELL")
line(tk,"taker"); line(m15,"15m"); line(sol,"sol")
line(allf,"TOTAL")
print("\n=== DURABILITY: cell, first-60% vs last-40% (is it one lucky run or persistent?) ===")
cell=sorted([f for f in zm if f["B"] and 0.90<=f["B"]<0.96],key=lambda x:x["ws"])
cut=cell[int(len(cell)*0.6)]["ws"]
line([f for f in cell if f["ws"]<cut],"cell TRAIN"); line([f for f in cell if f["ws"]>=cut],"cell HELD-OUT")
print("\n=== cell by coin (where the edge lives) ===")
line([f for f in cell if f["coin"]=="btc"],"cell btc"); line([f for f in cell if f["coin"]=="eth"],"cell eth")
# breakeven for the cell
cb=[f["B"] for f in cell if f["B"]]
print(f"\n  cell avg price {st.mean(cb):.3f} -> breakeven win% {st.mean(cb)*100:.1f}; actual win% {sum(1 for f in cell if f['won'])/len(cell)*100:.1f} (edge = actual - breakeven)")
print("\n=== VERDICT INPUTS ===")
print("  SOUND if: TOTAL PnL clearly +, cell win% > breakeven in BOTH train & held-out, edge consistent across coins.")
print("  THIN if: G low (~1-4%) -> real but small per-$ edge; scaling amplifies edge AND variance proportionally.")
