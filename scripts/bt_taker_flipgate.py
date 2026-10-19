"""bt_taker_flipgate.py — should the early_taker get a flip60 (choppiness) gate?
In-sample regime split showed calm flip60<0.40 = +$12.80/92% vs chop = -$48.62/79%. But in-sample regime
slices are the SAME trap as in-sample z-slices (see bt_taker_zgate: best full-sample gate went FLAT held-out).
So the ONLY thing that matters: does a "fire taker only when flip60 < thr" policy beat keep-ALL on net PnL on
BOTH full AND HELD-OUT (last 40% by window-start)? If the best full gate is flat/neg held-out -> in-sample mining.
Ordered by window-start (slug suffix) for a clean time split, identical methodology to bt_taker_zgate."""
import json, statistics as st
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
T=[]
for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    try:o=json.loads(l)
    except:continue
    if o.get("kind")=="entry" and o.get("won") is not None and o.get("flip60") is not None:
        try: ws=int(o["slug"].rsplit("-",1)[1])
        except: continue
        T.append({"ws":ws,"flip":float(o["flip60"]),"won":bool(o["won"]),
                  "pnl":float(o.get("pnl",0) or 0),"coin":o.get("coin")})
T.sort(key=lambda x:x["ws"])
n=len(T); wins=sum(1 for t in T if t["won"]); net=sum(t["pnl"] for t in T)
print(f"=== {n} real taker entries (with flip60), {wins} win ({wins/n*100:.1f}%), net ${net:+.2f} ===")
print("\n=== win% + net by flip60 bucket (in-sample reference) ===")
print(f"  {'flip band':12s} {'n':>4s} {'win%':>6s} {'net$':>9s} {'EV/sh':>7s}")
for lo,hi in [(0,0.30),(0.30,0.40),(0.40,0.45),(0.45,0.55),(0.55,9)]:
    b=[t for t in T if lo<=t["flip"]<hi]
    if b: print(f"  {lo:.2f}-{hi:<5.2f}{len(b):>4d} {sum(1 for t in b if t['won'])/len(b)*100:>5.1f} {sum(t['pnl'] for t in b):>+9.2f} {st.mean([t['pnl']/5 for t in b]):>+7.3f}")
def policy_net(data, keep):
    s=[t for t in data if keep(t)]
    return len(s), (sum(1 for t in s if t['won'])/len(s)*100 if s else 0), sum(t['pnl'] for t in s)
cut=int(n*0.6); train=T[:cut]; held=T[cut:]
print(f"\n  split: TRAIN first {cut} (ws<= {train[-1]['ws']}) | HELD-OUT last {len(held)} (ws>= {held[0]['ws']})")
print(f"\n=== GATE POLICIES: fire taker only when flip60 < thr — net on FULL / TRAIN(60%) / HELD-OUT(40%) ===")
print(f"  {'policy':22s} {'FULL n/win%/net':>22s} {'TRAIN net':>10s} {'HELDOUT net':>12s}")
def row(lab,keep):
    fn,fw,ff=policy_net(T,keep); _,_,tr=policy_net(train,keep); _,_,hd=policy_net(held,keep)
    print(f"  {lab:22s} {fn:>4d}/{fw:>4.1f}%/{ff:>+7.2f} {tr:>+10.2f} {hd:>+12.2f}")
row("keep ALL (baseline)", lambda t: True)
for thr in (0.30,0.40,0.45,0.55):
    row(f"keep flip< {thr}", lambda t,th=thr: t["flip"]<th)
# also report the baseline net split so HELDOUT gate is judged vs HELDOUT baseline, not full baseline
_,_,base_tr=policy_net(train,lambda t:True); _,_,base_hd=policy_net(held,lambda t:True)
print(f"\n  baseline TRAIN net=${base_tr:+.2f}  baseline HELDOUT net=${base_hd:+.2f}")
print("\nREAD: a flip-gate is deployable ONLY if it beats baseline net on BOTH full AND held-out.")
print("If the gate just cuts net on held-out (removes winners) or goes flat -> it's the in-sample regime trap; keep taker lead-only.")
