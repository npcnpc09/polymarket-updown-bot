"""eth_vs_btc.py — is eth genuinely more loss-prone than btc (RATE, not count)? And why? Compare real fills by
coin: win%/loss%/PnL/G, vol30, z, settle-margin, split cell vs taker. Tests: (1) is eth's loss RATE higher,
(2) is it a vol difference, (3) the 'eth follows btc' hypothesis (eth's own signal weaker = more reversals)."""
import json, statistics as st
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
fills=[]
for f,eng,keep in (("data/multi_window_engine_live.jsonl","cell/zmaker",lambda o:o.get("filled") is True and o.get("won") is not None),
                   ("data/early_taker_probe.jsonl","taker",lambda o:o.get("kind")=="entry" and o.get("won") is not None)):
    for o in (json.loads(l) for l in open(ROOT+"/"+f,encoding="utf-8") if l.strip()):
        if keep(o):
            w=ws_of(o.get("slug",""))
            if w and o.get("coin") in ("btc","eth"):
                sh=float(o.get("sh",5) or 5); B=float(o.get("B") or o.get("paid") or 0.8)
                fills.append({"eng":eng,"coin":o["coin"],"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),
                              "vol":o.get("vol30"),"z":o.get("zscore"),"lead":o.get("lead"),"risk":sh*B,"B":B})
def rep(s,lab):
    if not s: print(f"  {lab:22s} n=0"); return
    w=sum(1 for r in s if r["won"]); p=sum(r["pnl"] for r in s); risk=sum(r["risk"] for r in s)
    vols=[r["vol"] for r in s if r["vol"] is not None]
    print(f"  {lab:22s} n={len(s):4d} loss%={100-w/len(s)*100:5.1f} PnL=${p:+8.2f} G={p/risk*100 if risk else 0:+5.2f}% medVol={st.median(vols) if vols else 0:.1f}")
print("=== eth vs btc, ALL engines ===")
rep([r for r in fills if r["coin"]=="btc"],"btc ALL")
rep([r for r in fills if r["coin"]=="eth"],"eth ALL")
print("\n=== cell (zmaker) only ===")
rep([r for r in fills if r["coin"]=="btc" and r["eng"]=="cell/zmaker"],"btc cell/zmaker")
rep([r for r in fills if r["coin"]=="eth" and r["eng"]=="cell/zmaker"],"eth cell/zmaker")
print("\n=== taker only ===")
rep([r for r in fills if r["coin"]=="btc" and r["eng"]=="taker"],"btc taker")
rep([r for r in fills if r["coin"]=="eth" and r["eng"]=="taker"],"eth taker")
print("\n=== vol30 distribution (is eth higher-vol?) ===")
for c in ("btc","eth"):
    v=[r["vol"] for r in fills if r["coin"]==c and r["vol"] is not None]
    if v: print(f"  {c}: vol30 median={st.median(v):.1f} mean={st.mean(v):.1f} p90={sorted(v)[int(len(v)*0.9)]:.1f}")
print("\n=== loss rate by vol bucket, eth vs btc (does eth lose more AT SAME vol?) ===")
for c in ("btc","eth"):
    for lo,hi,lab in ((0,4,"vol<4"),(4,7,"vol4-7"),(7,99,"vol>=7")):
        s=[r for r in fills if r["coin"]==c and r["vol"] is not None and lo<=r["vol"]<hi]
        if s: print(f"  {c} {lab:8s}: n={len(s):3d} loss%={100-sum(1 for r in s if r['won'])/len(s)*100:4.1f}")
print("\nREAD: if eth loss% > btc AT THE SAME vol bucket -> eth is structurally worse (not just higher vol).")
print("If eth's higher loss is only because eth sits in higher-vol buckets -> it's a vol effect, not eth-specific.")
