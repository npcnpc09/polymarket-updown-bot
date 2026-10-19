"""why_losses.py — anatomy of the recent losing trades (both engines), with entry features +
what the lead did intra-window (entry lead vs peak lead vs final), to see if they're reversals."""
import json
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
LO=1782112000  # ~ since just before the high
def grab(fn,eng,pred):
    out=[]
    for l in open(ROOT+"/"+fn,encoding="utf-8"):
        if not l.strip(): continue
        try:o=json.loads(l)
        except:continue
        if pred(o):
            ws=int(o["slug"].rsplit("-",1)[1])
            if ws>=LO: out.append((eng,ws,o))
    return out
zm=grab("data/multi_window_engine_live.jsonl","zmaker",lambda o:o.get("filled") is True and o.get("won") is False)
tk=grab("data/early_taker_probe.jsonl","taker",lambda o:o.get("kind")=="entry" and o.get("won") is False)
allL=sorted(zm+tk,key=lambda x:x[1])
print(f"=== {len(allL)} losing trades since ws {LO} ===\n")
for eng,ws,o in allL:
    print(f"[{eng}] {o['slug']}  {o.get('coin')} {o.get('side')}  ${o.get('pnl')}")
    print(f"    entry B={o.get('B')} ask={o.get('ask')} sh={o.get('sh')}")
    print(f"    lead(entry/now)={o.get('lead')}  max_lead={o.get('max_lead')}  peak_old_side={o.get('old_side_peak')}")
    print(f"    zscore={o.get('zscore')} vol30={o.get('vol30')} persist={o.get('persist')}")
    print(f"    flips={o.get('flips')} sharp_flip={o.get('sharp_flip')} since_flip={o.get('since_flip')} flip_swing={o.get('flip_swing')}")
    print(f"    breaker={o.get('breaker')} deepcalm={o.get('deepcalm')} roll10={o.get('roll10')}")
    # taker-specific spike fields
    for k in ("lead2","offset","accel","reentry"):
        if o.get(k) is not None: print(f"    {k}={o.get(k)}")
    print()
# wins in same window for contrast
wz=grab("data/multi_window_engine_live.jsonl","zmaker",lambda o:o.get("filled") is True and o.get("won") is True)
wt=grab("data/early_taker_probe.jsonl","taker",lambda o:o.get("kind")=="entry" and o.get("won") is True)
allW=sorted(wz+wt,key=lambda x:x[1])
import statistics as st
def avg(xs,k):
    v=[o[k] for _,_,o in xs if o.get(k) is not None]
    return round(st.mean(v),2) if v else None
print("=== contrast: same-period WINS vs LOSSES (mean) ===")
for k in ("B","lead","max_lead","zscore","vol30","persist"):
    print(f"  {k:10s} win={avg(allW,k)}  loss={avg(allL,k)}")
print(f"  (wins n={len(allW)}, losses n={len(allL)})")
