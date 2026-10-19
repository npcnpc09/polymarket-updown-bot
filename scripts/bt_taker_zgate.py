"""bt_taker_zgate.py — should the early_taker get a z-score gate? It currently fires on lead>=8 only (no z).
Last night 3/4 losses were taker, 2 low-z. BUT memory has CONTRADICTORY in-sample taker-z findings, so the
decision rests on the HELD-OUT time split, not the in-sample curve. We test both directions (gate out low-z,
gate out high-z) and report net PnL of each policy on FULL, TRAIN(first 60%), HELD-OUT(last 40%)."""
import json, statistics as st
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
T=[]
for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    try:o=json.loads(l)
    except:continue
    if o.get("kind")=="entry" and o.get("won") is not None and o.get("zscore") is not None:
        try: ws=int(o["slug"].rsplit("-",1)[1])
        except: continue
        T.append({"ws":ws,"z":float(o["zscore"]),"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),"coin":o.get("coin")})
T.sort(key=lambda x:x["ws"])
n=len(T); wins=sum(1 for t in T if t["won"]); net=sum(t["pnl"] for t in T)
print(f"=== {n} real taker entries (with z), {wins} win ({wins/n*100:.1f}%), net ${net:+.2f} ===")
print("\n=== win% + net by z bucket ===")
print(f"  {'z band':10s} {'n':>4s} {'win%':>6s} {'net$':>9s} {'EV/sh':>7s}")
for lo,hi in [(0,1.5),(1.5,2),(2,2.5),(2.5,3),(3,4),(4,99)]:
    b=[t for t in T if lo<=t["z"]<hi]
    if b: print(f"  {lo:.1f}-{hi:<4.0f} {len(b):>4d} {sum(1 for t in b if t['won'])/len(b)*100:>5.1f} {sum(t['pnl'] for t in b):>+9.2f} {st.mean([t['pnl']/5 for t in b]):>+7.3f}")
def policy_net(data, keep):
    s=[t for t in data if keep(t)]
    return len(s), (sum(1 for t in s if t['won'])/len(s)*100 if s else 0), sum(t['pnl'] for t in s)
cut=int(n*0.6); train=T[:cut]; held=T[cut:]
print(f"\n=== GATE POLICIES: net on FULL / TRAIN(60%) / HELD-OUT(40%)  [baseline=keep all] ===")
print(f"  {'policy':22s} {'FULL n/win%/net':>22s} {'TRAIN net':>10s} {'HELDOUT net':>12s}")
def row(lab,keep):
    fn,fw,ff=policy_net(T,keep); _,_,tr=policy_net(train,keep); _,_,hd=policy_net(held,keep)
    print(f"  {lab:22s} {fn:>4d}/{fw:>4.1f}%/{ff:>+7.2f} {tr:>+10.2f} {hd:>+12.2f}")
row("keep ALL (baseline)", lambda t: True)
for thr in (1.5,2.0,2.5,3.0):
    row(f"keep z>= {thr}", lambda t,th=thr: t["z"]>=th)
for thr in (1.5,2.0,2.5):
    row(f"keep z<  {thr}", lambda t,th=thr: t["z"]<th)
print("\nREAD: a gate is only worth deploying if it beats baseline net on BOTH full AND held-out (not just in-sample/full).")
print("If the best full-sample gate is flat/negative on held-out -> it's in-sample mining (the documented taker-z trap); keep taker lead-only.")
