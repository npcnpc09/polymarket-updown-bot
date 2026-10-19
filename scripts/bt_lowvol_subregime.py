"""bt_lowvol_subregime.py — WITHIN the low-vol (<5) period, split the CELL fills into sub-regimes to find
which sub-conditions are PROFITABLE vs LOSING. Real live fills only. Axes: vol-fine / z / deepcalm(upsize) /
coin / side / persist / max_lead. Then held-out (60/40 by window-start) on the key splits.
Goal (user): don't just say 'low-vol cell good' — say WHICH low-vol sub-regimes win and which bleed."""
import json, statistics as st
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
C=[]
for l in open(ROOT+"/data/multi_window_engine_live.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    try:o=json.loads(l)
    except:continue
    if o.get("filled") and o.get("won") is not None and o.get("pnl") is not None and o.get("vol30") is not None:
        ws=ws_of(o.get("slug",""))
        if ws is None or float(o["vol30"])>=5: continue
        C.append({"ws":ws,"vol":float(o["vol30"]),"z":o.get("zscore"),"won":bool(o["won"]),
                  "pnl":float(o["pnl"]),"sh":float(o.get("sh",5) or 5),"coin":o.get("coin"),
                  "side":o.get("side"),"incell":bool(o.get("in_cell")),"deepcalm":bool(o.get("deepcalm")),
                  "breaker":bool(o.get("breaker")),"persist":o.get("persist"),"maxlead":o.get("max_lead"),
                  "lead":o.get("lead")})
C.sort(key=lambda x:x["ws"])
def stat(s):
    if not s: return "n=0"
    w=sum(1 for t in s if t["won"]); net=sum(t["pnl"] for t in s)
    ev=st.mean([t["pnl"]/t["sh"] for t in s])
    return "n={:4d} win%={:5.1f} net=${:+8.2f} EV/sh={:+.3f}".format(len(s),w/len(s)*100,net,ev)
print("=== LOW-VOL (<5) CELL fills: {} ===".format(len(C)))
print("\n--- by vol-fine ---")
for lab,lo,hi in [("<2.5",0,2.5),("2.5-3.5",2.5,3.5),("3.5-4.5",3.5,4.5),("4.5-5",4.5,5)]:
    print("  vol {:8s}: {}".format(lab,stat([r for r in C if lo<=r["vol"]<hi])))
print("\n--- by z (low-vol z can be inflated) ---")
for lab,lo,hi in [("2.5-3",2.5,3),("3-3.5",3,3.5),("3.5-4.5",3.5,4.5),(">=4.5",4.5,99)]:
    print("  z {:8s}: {}".format(lab,stat([r for r in C if r["z"] is not None and lo<=r["z"]<hi])))
print("\n--- deepcalm(upsized 20/28sh) vs normal vs breaker(downsized) ---")
print("  deepcalm : "+stat([r for r in C if r["deepcalm"]]))
print("  breaker  : "+stat([r for r in C if r["breaker"]]))
print("  normal   : "+stat([r for r in C if not r["deepcalm"] and not r["breaker"]]))
print("\n--- by coin x side ---")
for c in ("btc","eth"):
    for sd in ("Up","Down"):
        s=[r for r in C if r["coin"]==c and r["side"]==sd]
        if s: print("  {:4s} {:4s}: {}".format(c,sd,stat(s)))
print("\n--- by persist (trend persistence; higher = more sustained) ---")
pv=[r for r in C if r["persist"] is not None]
for lab,lo,hi in [("<0.4",0,0.4),("0.4-0.7",0.4,0.7),(">=0.7",0.7,99)]:
    print("  persist {:8s}: {}".format(lab,stat([r for r in pv if lo<=float(r["persist"])<hi])))
print("\n--- by |max_lead| (entry signal strength) ---")
ml=[r for r in C if r["maxlead"] is not None]
for lab,lo,hi in [("<10",0,10),("10-20",10,20),("20-40",20,40),(">=40",40,9999)]:
    print("  |maxlead| {:7s}: {}".format(lab,stat([r for r in ml if lo<=abs(float(r["maxlead"]))<hi])))
# held-out on the key candidate refinements
n=len(C); cut=int(n*0.6); tr=C[:cut]; hd=C[cut:]
def pol(d,keep):
    s=[t for t in d if keep(t)]; return (len(s),sum(t["pnl"] for t in s),(st.mean([t['pnl']/t['sh'] for t in s]) if s else 0))
print("\n=== held-out on refinements (FULL / TRAIN / HELDOUT) ===")
def row(lab,keep):
    fn,ff,fe=pol(C,keep); _,tf,te=pol(tr,keep); hn,hf,he=pol(hd,keep)
    print("  {:30s} FULL {:4d}/${:+7.2f}/{:+.3f} | TRAIN ${:+7.2f}/{:+.3f} | HELD {:4d}/${:+7.2f}/{:+.3f}".format(lab,fn,ff,fe,tf,te,hn,hf,he))
row("all low-vol cell", lambda t: True)
row("exclude deepcalm", lambda t: not t["deepcalm"])
row("exclude vol 4.5-5 band", lambda t: not (4.5<=t["vol"]<5))
row("btc only", lambda t: t["coin"]=="btc")
row("persist>=0.4", lambda t: t["persist"] is not None and float(t["persist"])>=0.4)
row("no-deepcalm & persist>=0.4", lambda t: (not t["deepcalm"]) and t["persist"] is not None and float(t["persist"])>=0.4)
print("\nREAD: find sub-regimes with clearly +EV vs <=0 EV. deepcalm=upsize-in-calm (air-pocket risk), persist=trend follow-through.")
