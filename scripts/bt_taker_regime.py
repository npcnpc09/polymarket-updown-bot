"""bt_taker_regime.py — taker win%/net across MARKET REGIME x z-ratio. Regime axes from logged fields:
btc_vol (validated vol-regime, memory VOL_CAP~6.5) and flip60 (choppiness: frac of recent flips).
'比' = zscore (lead/vol). Question: is the taker's z-edge / its bleed regime-conditional?
Only the z-logged subset (~323 recent entries) has these fields. Small cells -> report n, read cautiously."""
import json, statistics as st
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
T=[]
for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    try:o=json.loads(l)
    except:continue
    if o.get("kind")=="entry" and o.get("won") is not None and o.get("zscore") is not None:
        T.append({"z":float(o["zscore"]),"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),
                  "bvol":o.get("btc_vol"),"flip":o.get("flip60"),"cvol":o.get("coin_vol30"),"coin":o.get("coin")})
n=len(T)
def stat(s):
    if not s: return "  (none)"
    w=sum(1 for t in s if t["won"]); return f"n={len(s):3d} win%={w/len(s)*100:5.1f} net=${sum(t['pnl'] for t in s):+8.2f} EV/sh={st.mean([t['pnl']/5 for t in s]):+.3f}"
print(f"=== taker z-logged subset: {n} entries, net ${sum(t['pnl'] for t in T):+.2f} ===")
print("\n=== 1D by btc_vol regime ===")
for lab,lo,hi in [("low  <5",0,5),("mid 5-6.5",5,6.5),("HIGH >=6.5",6.5,99)]:
    print(f"  btc_vol {lab:10s}: "+stat([t for t in T if t['bvol'] is not None and lo<=t['bvol']<hi]))
print("\n=== 1D by flip60 (choppiness) ===")
for lab,lo,hi in [("calm <0.40",0,0.40),("mid .40-.55",0.40,0.55),("CHOP >=0.55",0.55,9)]:
    print(f"  flip60 {lab:12s}: "+stat([t for t in T if t['flip'] is not None and lo<=t['flip']<hi]))
print("\n=== 1D by z-ratio ===")
for lab,lo,hi in [("z<1.5",0,1.5),("z1.5-2.5",1.5,2.5),("z>=2.5",2.5,99)]:
    print(f"  {lab:10s}: "+stat([t for t in T if lo<=t['z']<hi]))
print("\n=== 2D: btc_vol regime x z-ratio (win% / net) ===")
print(f"  {'':12s} {'z<1.5':>16s} {'z1.5-2.5':>16s} {'z>=2.5':>16s}")
for rlab,rlo,rhi in [("vol<6.5",0,6.5),("vol>=6.5",6.5,99)]:
    cells=[]
    for zlo,zhi in [(0,1.5),(1.5,2.5),(2.5,99)]:
        s=[t for t in T if t['bvol'] is not None and rlo<=t['bvol']<rhi and zlo<=t['z']<zhi]
        if s: w=sum(1 for t in s if t['won']); cells.append(f"{w}/{len(s)} {sum(t['pnl'] for t in s):+.0f}")
        else: cells.append("-")
    print(f"  {rlab:12s} {cells[0]:>16s} {cells[1]:>16s} {cells[2]:>16s}")
print("\n=== 2D: flip60 regime x z-ratio (win% / net) ===")
print(f"  {'':12s} {'z<1.5':>16s} {'z1.5-2.5':>16s} {'z>=2.5':>16s}")
for rlab,rlo,rhi in [("calm<0.45",0,0.45),("chop>=0.45",0.45,9)]:
    cells=[]
    for zlo,zhi in [(0,1.5),(1.5,2.5),(2.5,99)]:
        s=[t for t in T if t['flip'] is not None and rlo<=t['flip']<rhi and zlo<=t['z']<zhi]
        if s: w=sum(1 for t in s if t['won']); cells.append(f"{w}/{len(s)} {sum(t['pnl'] for t in s):+.0f}")
        else: cells.append("-")
    print(f"  {rlab:12s} {cells[0]:>16s} {cells[1]:>16s} {cells[2]:>16s}")
print("\nREAD: look for cells that are consistently +net (deploy zone) vs consistently -net (avoid zone).")
print("Small n per cell -> directional only, not deployable without held-out confirmation.")
