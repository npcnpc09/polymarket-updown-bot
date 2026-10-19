"""bt_winning_regime.py — INVERT the question: instead of mining a forward gate, just DESCRIBE the market
regime during the stretches we actually made money vs lost it. Pure description (in-sample, honest about that).
Combines taker (early_taker_probe.jsonl) + cell/zmaker (multi_window_engine_live.jsonl) settled fills.
Shared regime axes: coin vol (coin_vol30 / vol30), zscore. flip60 + btc_vol are taker-only.
Sort by window-start, build cumulative PnL arc, split at PEAK into UP-ARC vs DRAWDOWN, compare fingerprints.
Also per-day net + median regime so the user can see 'profitable day looked like X'."""
import json, statistics as st
from collections import defaultdict
from datetime import datetime, timezone
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(slug):
    try: return int(slug.rsplit("-",1)[1])
    except: return None
rows=[]
# taker
for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    try:o=json.loads(l)
    except:continue
    if o.get("kind")=="entry" and o.get("won") is not None:
        ws=ws_of(o.get("slug",""));
        if ws is None: continue
        rows.append({"ws":ws,"eng":"taker","won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),
                     "vol":o.get("coin_vol30"),"bvol":o.get("btc_vol"),"flip":o.get("flip60"),"z":o.get("zscore")})
# cell/zmaker live
for l in open(ROOT+"/data/multi_window_engine_live.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    try:o=json.loads(l)
    except:continue
    if o.get("filled") and o.get("won") is not None and o.get("pnl") is not None:
        ws=ws_of(o.get("slug",""));
        if ws is None: continue
        rows.append({"ws":ws,"eng":"cell","won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),
                     "vol":o.get("vol30"),"bvol":None,"flip":None,"z":o.get("zscore")})
rows.sort(key=lambda x:x["ws"])
n=len(rows); net=sum(r["pnl"] for r in rows)
print(f"=== {n} settled fills (taker+cell), net ${net:+.2f} ===")
# cumulative arc + peak
cum=0; peak=-1e9; peak_i=0
for i,r in enumerate(rows):
    cum+=r["pnl"]
    if cum>peak: peak=cum; peak_i=i
up=rows[:peak_i+1]; dn=rows[peak_i+1:]
def med(s,k):
    v=[x[k] for x in s if x.get(k) is not None]
    return st.median(v) if v else None
def fp(s,lab):
    if not s: print(f"  {lab}: (none)"); return
    w=sum(1 for x in s if x["won"]); pnl=sum(x["pnl"] for x in s)
    mv=med(s,"vol"); mb=med(s,"bvol"); mf=med(s,"flip"); mz=med(s,"z")
    fmt=lambda x: f"{x:.2f}" if x is not None else "  - "
    print(f"  {lab:14s} n={len(s):3d} win%={w/len(s)*100:5.1f} net=${pnl:+8.2f} | med coin_vol={fmt(mv)} btc_vol={fmt(mb)} flip60={fmt(mf)} z={fmt(mz)}")
print(f"\n=== ARC SPLIT at peak (entry #{peak_i+1}, peak cum=${peak:+.2f}) ===")
fp(up,"UP-ARC")
fp(dn,"DRAWDOWN")
# direct: winning fills vs losing fills regime (the bluntest cut)
print(f"\n=== winning fills vs losing fills (blunt) ===")
fp([r for r in rows if r["won"]],"WINNERS")
fp([r for r in rows if not r["won"]],"LOSERS")
# taker-only flip60 split (flip is the choppiness axis, taker-only)
tk=[r for r in rows if r["eng"]=="taker" and r["flip"] is not None]
print(f"\n=== taker-only: net by flip60 (choppiness) — the 'calm vs chop' axis ===")
for lab,lo,hi in [("calm <0.40",0,0.40),("mid .40-.50",0.40,0.50),("chop .50-.55",0.50,0.55),("CHOP >=0.55",0.55,9)]:
    s=[r for r in tk if lo<=r["flip"]<hi]
    if s: w=sum(1 for x in s if x["won"]); print(f"  flip {lab:12s} n={len(s):3d} win%={w/len(s)*100:5.1f} net=${sum(x['pnl'] for x in s):+8.2f}")
# per-day net + regime fingerprint
print(f"\n=== per-day net + median regime (UTC day) ===")
byday=defaultdict(list)
for r in rows: byday[datetime.fromtimestamp(r["ws"],tz=timezone.utc).strftime("%m-%d")].append(r)
print(f"  {'day':6s} {'n':>4s} {'win%':>6s} {'net$':>9s} {'coin_vol':>9s} {'btc_vol':>8s} {'flip60':>7s} {'z':>5s}")
for d in sorted(byday):
    s=byday[d]; w=sum(1 for x in s if x["won"])
    def m(k):
        v=[x[k] for x in s if x.get(k) is not None]; return f"{st.median(v):.2f}" if v else "  -"
    print(f"  {d:6s} {len(s):>4d} {w/len(s)*100:>5.1f} {sum(x['pnl'] for x in s):>+9.2f} {m('vol'):>9s} {m('bvol'):>8s} {m('flip'):>7s} {m('z'):>5s}")
print("\nREAD: this is DESCRIPTIVE (in-sample) — the point is to SEE the winning-regime fingerprint, not to deploy a gate.")
