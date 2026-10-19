"""win_vs_loss_15m.py — what distinguishes 15m winners from losers? And the KEY question for the
user's idea: does higher 'certainty' actually have higher EV, or just higher win% (priced-in)?
The trap: a higher-price favorite wins more often but pays less and loses more $ -> sizing up there
can be profit-NEGATIVE even at 95% win. So I report, per feature bucket: win% AND mean pnl PER SHARE
(EV/sh = the only thing that matters for sizing)."""
import json, statistics as st
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
rows=[]
for l in open(ROOT+"/data/multi_window_engine_15m_live.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    try: o=json.loads(l)
    except: continue
    if o.get("filled") is True and o.get("won") is not None:
        sh=float(o.get("sh",5) or 5)
        o["_evsh"]=float(o.get("pnl",0) or 0)/sh   # pnl per share = EV/sh
        rows.append(o)
W=[o for o in rows if o["won"]]; L=[o for o in rows if not o["won"]]
def m(xs,k):
    v=[o[k] for o in xs if o.get(k) is not None]
    return st.mean(v) if v else float("nan")
print(f"=== {len(rows)} fills: {len(W)} win / {len(L)} loss ===\n")
print(f"{'feature':12s} {'WIN mean':>10s} {'LOSS mean':>10s}")
for k in ("B","ask","lead","max_lead","persist","zscore","vol30","flips"):
    print(f"{k:12s} {m(W,k):>10.2f} {m(L,k):>10.2f}")

print("\n=== EV PER SHARE by ENTRY PRICE bucket (the user's 'certainty' = price) ===")
print("  higher price = higher 'certainty'/win% but worse payoff asymmetry. EV/sh is what matters for sizing.")
print(f"  {'price band':12s} {'n':>4s} {'win%':>6s} {'EV/sh':>8s} {'totPnL@5sh':>11s}")
bands=[(0.80,0.85),(0.85,0.90),(0.90,0.93),(0.93,0.96),(0.96,1.01)]
for lo,hi in bands:
    b=[o for o in rows if o.get("B") is not None and lo<=o["B"]<hi]
    if not b: continue
    w=sum(1 for o in b if o["won"])/len(b)*100
    ev=st.mean([o["_evsh"] for o in b])
    print(f"  {lo:.2f}-{hi:.2f}    {len(b):>4d} {w:>6.1f} {ev:>+8.3f} {ev*5*len(b):>+11.2f}")

print("\n=== EV PER SHARE by ZSCORE bucket (signal-strength 'certainty', orthogonal-ish to price) ===")
print(f"  {'z band':12s} {'n':>4s} {'win%':>6s} {'EV/sh':>8s} {'meanB':>6s}")
zb=[(2.5,3.0),(3.0,4.0),(4.0,6.0),(6.0,99)]
for lo,hi in zb:
    b=[o for o in rows if o.get("zscore") is not None and lo<=o["zscore"]<hi]
    if not b: continue
    w=sum(1 for o in b if o["won"])/len(b)*100
    ev=st.mean([o["_evsh"] for o in b]); mb=st.mean([o["B"] for o in b if o.get("B")])
    print(f"  {lo:.1f}-{hi:<5.0f}  {len(b):>4d} {w:>6.1f} {ev:>+8.3f} {mb:>6.2f}")

print("\n=== EV PER SHARE by MAX_LEAD bucket ===")
print(f"  {'maxlead':12s} {'n':>4s} {'win%':>6s} {'EV/sh':>8s} {'meanB':>6s}")
for lo,hi in [(0,10),(10,15),(15,25),(25,999)]:
    b=[o for o in rows if o.get("max_lead") is not None and lo<=o["max_lead"]<hi]
    if not b: continue
    w=sum(1 for o in b if o["won"])/len(b)*100
    ev=st.mean([o["_evsh"] for o in b]); mb=st.mean([o["B"] for o in b if o.get("B")])
    print(f"  {lo:>3d}-{hi:<5d}  {len(b):>4d} {w:>6.1f} {ev:>+8.3f} {mb:>6.2f}")
print("\nKEY: a bucket only deserves MORE size if its EV/sh is clearly HIGHER, not just its win%.")
