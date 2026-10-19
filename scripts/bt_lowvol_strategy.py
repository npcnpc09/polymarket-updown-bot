"""bt_lowvol_strategy.py — design+backtest a LOW-VOL-CALM-period strategy from REAL live fills (not paper).
Question: in low-vol calm periods (where the macro-trend resume gate keeps us flat), do our REAL fills make
money, and what subset is +EV and HELD-OUT stable? Uses cell (multi_window_engine_live) + taker
(early_taker_probe) real settled fills. vol = vol30 (cell) / coin_vol30 (taker). EV/sh = pnl/sh.
Time-split (60/40 by window-start) to guard against in-sample mining (memory: no filter w/o held-out)."""
import json, statistics as st
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
R=[]
# cell
for l in open(ROOT+"/data/multi_window_engine_live.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    try:o=json.loads(l)
    except:continue
    if o.get("filled") and o.get("won") is not None and o.get("pnl") is not None:
        ws=ws_of(o.get("slug",""))
        if ws is None: continue
        sh=float(o.get("sh",5) or 5)
        R.append({"ws":ws,"eng":"cell","vol":o.get("vol30"),"z":o.get("zscore"),
                  "won":bool(o["won"]),"pnl":float(o["pnl"]),"sh":sh,"coin":o.get("coin"),
                  "incell":bool(o.get("in_cell"))})
# taker
for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    try:o=json.loads(l)
    except:continue
    if o.get("kind")=="entry" and o.get("won") is not None:
        ws=ws_of(o.get("slug",""))
        if ws is None: continue
        R.append({"ws":ws,"eng":"taker","vol":o.get("coin_vol30"),"z":o.get("zscore"),
                  "won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),"sh":5.0,"coin":o.get("coin"),
                  "incell":False})
R=[r for r in R if r["vol"] is not None]
R.sort(key=lambda x:x["ws"])
def stat(s):
    if not s: return "n=0"
    w=sum(1 for t in s if t["won"]); net=sum(t["pnl"] for t in s)
    ev=st.mean([t["pnl"]/t["sh"] for t in s])
    return "n={:4d} win%={:5.1f} net=${:+8.2f} EV/sh={:+.3f}".format(len(s),w/len(s)*100,net,ev)
print("=== ALL real fills: {} (cell+taker) ===".format(len(R)))
print("\n--- by vol band (both engines) ---")
for lab,lo,hi in [("vol<3",0,3),("3-4",3,4),("4-5",4,5),("5-6",5,6),("6-8",6,8),(">=8",8,99)]:
    print("  vol {:7s}: {}".format(lab,stat([r for r in R if lo<=r["vol"]<hi])))
print("\n--- LOW-VOL (<5) subset, split by engine ---")
lv=[r for r in R if r["vol"]<5]
print("  cell  : "+stat([r for r in lv if r["eng"]=="cell"]))
print("  taker : "+stat([r for r in lv if r["eng"]=="taker"]))
print("  cell in_cell(0.90-0.95) : "+stat([r for r in lv if r["eng"]=="cell" and r["incell"]]))
print("\n--- LOW-VOL (<5) subset, by z ---")
for lab,lo,hi in [("z<1.5",0,1.5),("1.5-2.5",1.5,2.5),(">=2.5",2.5,99)]:
    print("  z {:9s}: {}".format(lab,stat([r for r in lv if r["z"] is not None and lo<=r["z"]<hi])))
print("\n--- LOW-VOL (<5) subset, by coin ---")
for c in ("btc","eth","sol","xrp","doge","bnb"):
    s=[r for r in lv if r["coin"]==c]
    if s: print("  {:5s}: {}".format(c,stat(s)))
# candidate low-vol strategies, held-out
n=len(R); cut=int(n*0.6); train=R[:cut]; held=R[cut:]
def pol(data,keep):
    s=[t for t in data if keep(t)];
    return (len(s), sum(t["pnl"] for t in s), (st.mean([t['pnl']/t['sh'] for t in s]) if s else 0))
print("\n=== CANDIDATE low-vol rules: net (EV/sh) on FULL / TRAIN(60%) / HELDOUT(40%) ===")
def row(lab,keep):
    fn,ff,fe=pol(R,keep); tn,tf,te=pol(train,keep); hn,hf,he=pol(held,keep)
    print("  {:34s} FULL {:4d}/${:+7.2f}/{:+.3f} | TRAIN ${:+7.2f} | HELD {:4d}/${:+7.2f}/{:+.3f}".format(lab,fn,ff,fe,tf,hn,hf,he))
row("baseline: ALL fills", lambda t: True)
row("vol<5 (any)", lambda t: t["vol"]<5)
row("vol<5 & cell", lambda t: t["vol"]<5 and t["eng"]=="cell")
row("vol<5 & cell & in_cell", lambda t: t["vol"]<5 and t["eng"]=="cell" and t["incell"])
row("vol<5 & z>=2.5", lambda t: t["vol"]<5 and t["z"] is not None and t["z"]>=2.5)
row("vol<5 & cell & z>=2.5", lambda t: t["vol"]<5 and t["eng"]=="cell" and t["z"] is not None and t["z"]>=2.5)
row("vol<4 & cell & z>=2.5", lambda t: t["vol"]<4 and t["eng"]=="cell" and t["z"] is not None and t["z"]>=2.5)
row("vol<5 & taker", lambda t: t["vol"]<5 and t["eng"]=="taker")
print("\nREAD: a low-vol rule is worth deploying only if net>0 AND EV/sh>0 on BOTH full AND held-out.")
print("Compare cell vs taker in low-vol; in_cell(0.90-0.95) is the cell's core. btc/eth are the real coins (alt = noise).")
