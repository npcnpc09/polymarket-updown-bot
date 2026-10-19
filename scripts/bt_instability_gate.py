"""bt_instability_gate.py — test the user's insight: the breaker THRASHING (0<->arm repeatedly) is itself
a choppy-regime signal, and the current memoryless breaker gets whipsawed into upsizing to 28sh on a
MOMENTARY roll10==0 inside a choppy block ('false calm') -> the big air-pockets.
FIX tested: gate the deep-calm 28sh upsize on SUSTAINED calm -> only allow 28sh if NO armed state
(roll10>=2) occurred in the last T minutes; otherwise cap at 20sh (normal). Breaker(5sh)/normal(20sh) unchanged.
Re-simulate PnL on real cell fills (B, won) under CURRENT vs GATED policy. Report net, held-out, and the
LOSS TAIL (worst losses, deepcalm-tier loss sum). Diagnostic: do 'false-calm' deepcalm fills underperform
'sustained-calm' ones?"""
import json, statistics as st
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
cell=[]
for l in open(ROOT+"/data/multi_window_engine_live.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    try:o=json.loads(l)
    except:continue
    if o.get("filled") is True and o.get("won") is not None and o.get("roll10") is not None and o.get("B"):
        if 0.90<=o["B"]<0.96:  # the cell band where 5/20/28 tiering applies
            try: ws=int(o["slug"].rsplit("-",1)[1])
            except: continue
            cell.append({"ws":ws,"B":float(o["B"]),"won":bool(o["won"]),"roll":int(o["roll10"]),"coin":o.get("coin")})
cell.sort(key=lambda x:x["ws"])
print(f"=== {len(cell)} cell fills (B 0.90-0.96, roll10 logged) ===")
def size_cur(c): r=c["roll"]; return 5 if r>=2 else (28 if r==0 else 20)
def pnl(B,won,s): return (1-B)*s if won else -B*s
T=90*60  # 'recently armed' lookback seconds
def recently_armed(i):
    w0=cell[i]["ws"]-T
    for j in range(i-1,-1,-1):
        if cell[j]["ws"]<w0: break
        if cell[j]["roll"]>=2: return True
    return False
for c in cell: c["arm_recent"]=False
for i in range(len(cell)): cell[i]["arm_recent"]=recently_armed(i)
def size_gated(c):
    r=c["roll"]
    if r>=2: return 5
    if r==1: return 20
    return 20 if c["arm_recent"] else 28   # roll==0: gate deepcalm on sustained calm
# diagnostic: deepcalm fills split
dc=[c for c in cell if c["roll"]==0]
sus=[c for c in dc if not c["arm_recent"]]; fc=[c for c in dc if c["arm_recent"]]
def wr(g): return sum(1 for c in g if c["won"])/len(g)*100 if g else 0
def evsh(g): return st.mean([pnl(c["B"],c["won"],1) for c in g]) if g else 0
print(f"\n=== DIAGNOSTIC: deep-calm (roll10==0) fills, sustained-calm vs false-calm(recently armed <{T//60}min) ===")
print(f"  sustained-calm: n={len(sus):3d} win%={wr(sus):5.1f} EV/sh={evsh(sus):+.3f} worstLoss={min([pnl(c['B'],c['won'],28) for c in sus],default=0):+.2f}")
print(f"  FALSE-calm    : n={len(fc):3d} win%={wr(fc):5.1f} EV/sh={evsh(fc):+.3f} worstLoss={min([pnl(c['B'],c['won'],28) for c in fc],default=0):+.2f}")
print("  (if false-calm win%/EV clearly worse -> the thrash-gate is justified)")
def run(sizef,s):
    tot=sum(pnl(c["B"],c["won"],sizef(c)) for c in s)
    losses=sorted([pnl(c["B"],c["won"],sizef(c)) for c in s if not c["won"]])
    return tot,(losses[:3] if losses else []),sum(losses)
cut=int(len(cell)*0.6)
for lab,s in [("FULL",cell),("HELD-OUT last40%",cell[cut:])]:
    tc,wc,lc=run(size_cur,s); tg,wg,lg=run(lambda c:size_gated(c),s)
    print(f"\n=== {lab} (n={len(s)}) ===")
    print(f"  CURRENT (5/20/28):     net=${tc:+8.2f}  lossSum=${lc:+8.2f}  worst3={['%.1f'%x for x in wc]}")
    print(f"  GATED (28 only if sustained-calm): net=${tg:+8.2f}  lossSum=${lg:+8.2f}  worst3={['%.1f'%x for x in wg]}")
    print(f"  delta net = ${tg-tc:+.2f}   tail(lossSum) change = ${lg-lc:+.2f}")
print(f"\nupsizes suppressed: {sum(1 for c in cell if c['roll']==0 and c['arm_recent'])}/{len(dc)} deep-calm fills (28->20)")
