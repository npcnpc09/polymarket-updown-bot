"""dry_recent.py — DRY paper performance over the last N hours (default 8h), by hour / coin / gate.
Reads the DRY collectors' would-be fills (no real money). Helps judge whether sitting out cost us
money (engine self-gate is profitable) or correctly avoided losses, especially in the dead-calm stretch."""
import json, sys, time
from collections import defaultdict
from datetime import datetime, timezone
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
HRS=float(sys.argv[1]) if len(sys.argv)>1 else 8.0
NOW=int(time.time())
SINCE=NOW-int(HRS*3600)
def load(fn):
    out=[]
    try: f=open(ROOT+"/data/"+fn,encoding="utf-8")
    except FileNotFoundError: return out
    for l in f:
        if not l.strip(): continue
        try:o=json.loads(l)
        except:continue
        ts=o.get("ts")
        if ts is None or ts<SINCE: continue
        if o.get("won") is None: continue
        out.append(o)
    return out
def f(x): return float(x or 0)
for fn in ("alt_exec_dry.jsonl","alt_exec_dry_15m.jsonl"):
    rows=load(fn)
    print("==== {} : last {:.0f}h, n={} ====".format(fn,HRS,len(rows)))
    if not rows:
        print("  (no settled rows in window)"); continue
    tk=sum(f(r.get("taker_pnl")) for r in rows)
    mk=sum(f(r.get("maker_pnl")) for r in rows if r.get("maker_filled"))
    w=sum(1 for r in rows if r.get("won"))
    print("  TOTAL win%={:.0f}  taker=${:+.2f}  maker=${:+.2f}".format(w/len(rows)*100,tk,mk))
    byh=defaultdict(list)
    for r in rows: byh[datetime.fromtimestamp(r["ts"],tz=timezone.utc).strftime("%H")].append(r)
    print("  hour  n  win%  taker$  maker$  avgCvol")
    for h in sorted(byh):
        s=byh[h]; ww=sum(1 for r in s if r.get("won"))
        t=sum(f(r.get("taker_pnl")) for r in s)
        m=sum(f(r.get("maker_pnl")) for r in s if r.get("maker_filled"))
        cv=[f(r.get("cvol")) for r in s if r.get("cvol") is not None]
        acv=(sum(cv)/len(cv)) if cv else 0
        print("   {} {:3d} {:4.0f} {:+6.2f} {:+6.2f}  {:.1f}".format(h,len(s),ww/len(s)*100,t,m,acv))
    byc=defaultdict(list)
    for r in rows: byc[r.get("slug","").split("-")[0]].append(r)
    print("  by-coin taker$: "+" ".join("{}={:+.1f}".format(c,sum(f(r.get('taker_pnl')) for r in s)) for c,s in sorted(byc.items())))
    g=[r for r in rows if r.get("gate_ok")]; ng=[r for r in rows if not r.get("gate_ok")]
    if g or ng:
        print("  gate_ok=True n={} taker=${:+.2f} | gate_ok=False n={} taker=${:+.2f}".format(len(g),sum(f(r.get('taker_pnl')) for r in g),len(ng),sum(f(r.get('taker_pnl')) for r in ng)))
