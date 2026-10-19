"""dry_today_btceth.py — DRY paper PnL for TODAY (UTC date), btc/eth ONLY (the real coins), 5m + 15m collectors.
Splits by coin and by side (Up/Down) to compare against the sub-regime map (btc>eth, eth-Down weak)."""
import json
from datetime import datetime, timezone
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
# today UTC 00:00
import time
now=time.gmtime()
SOD=int(time.mktime((now.tm_year,now.tm_mon,now.tm_mday,0,0,0,0,0,0)))-time.timezone
def f(x): return float(x or 0)
def load(fn):
    out=[]
    try: fh=open(ROOT+"/data/"+fn,encoding="utf-8")
    except FileNotFoundError: return out
    for l in fh:
        if not l.strip(): continue
        try:o=json.loads(l)
        except:continue
        ts=o.get("ts")
        if ts is None or ts<SOD: continue
        if o.get("won") is None: continue
        coin=o.get("slug","").split("-")[0]
        if coin not in ("btc","eth"): continue
        out.append(o)
    return out
def rep(s,lab):
    if not s: print("  {:16s}: n=0".format(lab)); return
    w=sum(1 for r in s if r.get("won")); tk=sum(f(r.get("taker_pnl")) for r in s)
    mk=sum(f(r.get("maker_pnl")) for r in s if r.get("maker_filled"))
    print("  {:16s}: n={:3d} win%={:5.1f} taker=${:+7.2f} maker=${:+7.2f}".format(lab,len(s),w/len(s)*100,tk,mk))
print("=== DRY paper TODAY (UTC), btc/eth only ===")
for fn in ("alt_exec_dry.jsonl","alt_exec_dry_15m.jsonl"):
    rows=load(fn)
    print("\n--- {} : n={} ---".format(fn,len(rows)))
    if not rows: continue
    rep(rows,"ALL btc+eth")
    for c in ("btc","eth"):
        cs=[r for r in rows if r.get("slug","").startswith(c)]
        rep(cs,c)
        for sd in ("Up","Down"):
            rep([r for r in cs if r.get("side")==sd], "  "+c+" "+sd)
