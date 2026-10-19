"""bt_deepcalm_worth.py — is the deep-calm 28sh tier worth it vs capping the cell at 20? Reconstruct combined
(taker+zmaker) roll10 before each REAL cell fill, classify the tier under each policy, recompute PnL (sizing is
a counterfactual multiplier on real won/B). Isolate the 28-vs-20 increment on calm (roll10==0) cells: it's +EV
iff those cells win > B (~93%). The -$25.20 air-pocket was a roll10==0 deep-calm 28 -> does the calm bucket
still clear its bar overall?"""
import json
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
comb=[]; cells=[]
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl",encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None:
        w=ws_of(o.get("slug",""))
        if w:
            comb.append({"ws":w,"won":bool(o["won"])})
            if o.get("B") and 0.90<=o["B"]<0.96: cells.append({"ws":w,"won":bool(o["won"]),"B":float(o["B"])})
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8") if l.strip()):
    if o.get("kind")=="entry" and o.get("won") is not None:
        w=ws_of(o.get("slug",""))
        if w: comb.append({"ws":w,"won":bool(o["won"])})
comb.sort(key=lambda x:x["ws"]); cells.sort(key=lambda x:x["ws"])
def roll10(ws):
    prior=[f for f in comb if f["ws"]<ws][-10:]
    return sum(1 for f in prior if not f["won"]), len(prior)
def pnl(sh,won,B): return sh*(1-B) if won else -sh*B
for c in cells:
    r,n=roll10(c["ws"]); c["roll"]=r; c["armed"]=(n>=10)
# the deep-calm increment: roll10==0 cells, 28 vs 20
calm=[c for c in cells if c["armed"] and c["roll"]==0]
cw=sum(1 for c in calm if c["won"])
inc=sum(pnl(28,c["won"],c["B"])-pnl(20,c["won"],c["B"]) for c in calm)
print(f"=== DEEP-CALM cells (roll10==0): n={len(calm)} win%={cw/len(calm)*100:.1f} avgB={sum(c['B'] for c in calm)/len(calm):.3f} ===")
print(f"  breakeven win% for 28>20 increment = avgB = {sum(c['B'] for c in calm)/len(calm)*100:.1f}%")
print(f"  28-vs-20 INCREMENT (the deep-calm bet) = ${inc:+.2f} over {len(calm)} calm cells (${inc/len(calm):+.3f}/cell)")
print(f"  (losses in calm bucket: {len(calm)-cw}, each costs 8*B~${8*0.93:.1f} extra at 28 vs 20)")
def policy(c):
    if not c["armed"]: return 20
    if c["roll"]>=2: return 5
    if c["roll"]==0: return 28
    return 20
def policy_nodc(c):  # no deep-calm: cap at 20
    if c["armed"] and c["roll"]>=2: return 5
    return 20
def total(fn,s): return sum(pnl(fn(c),c["won"],c["B"]) for c in s)
print(f"\n=== total CELL PnL under each policy (n={len(cells)}) ===")
print(f"  flat-20            ${total(lambda c:20,cells):+8.2f}")
print(f"  no-deepcalm (20/5) ${total(policy_nodc,cells):+8.2f}")
print(f"  current 3-tier (28/20/5) ${total(policy,cells):+8.2f}")
cut=cells[int(len(cells)*0.6)]["ws"]
print(f"\n=== held-out (last 40%) ===")
ho=[c for c in cells if c["ws"]>=cut]
print(f"  no-deepcalm ${total(policy_nodc,ho):+.2f}  vs  3-tier ${total(policy,ho):+.2f}  (n={len(ho)})")
print("\nREAD: deep-calm worth it iff calm-bucket win% > avgB AND 3-tier total >= no-deepcalm in full & held-out.")
print("If the calm increment is negative / held-out worse -> cap the cell at 20 (drop the 28 tier).")
