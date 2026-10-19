"""taker_regime_diag.py — is there a REGIME that hurts the taker specifically? Split recent taker fills by the
logged regime axes (btc_vol, flip60) and compare win%/PnL on GREEN taker-days vs RED taker-days. Also: were
the red-day losses in the vol>=6.5 zone (the gate should catch) or vol<6.5 (gate-proof / irreducible)?"""
import json
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
tk=[]
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8") if l.strip()):
    if o.get("kind")=="entry" and o.get("won") is not None:
        w=ws_of(o.get("slug",""))
        if w: tk.append({"day":datetime.fromtimestamp(w,timezone.utc).strftime("%m-%d"),"won":bool(o["won"]),
                         "pnl":float(o.get("pnl",0) or 0),"bvol":o.get("btc_vol"),"flip":o.get("flip60"),
                         "paid":o.get("paid"),"coin":o.get("coin")})
RED={"06-17","06-19"}; GREEN={"06-15","06-16","06-18"}
def rep(s,lab):
    if not s: print(f"  {lab:24s} n=0"); return
    w=sum(1 for r in s if r["won"]); p=sum(r["pnl"] for r in s)
    print(f"  {lab:24s} n={len(s):3d} win%={w/len(s)*100:5.1f} PnL=${p:+7.2f}")
def vstat(s,lab):
    import statistics as st
    bv=[r["bvol"] for r in s if r["bvol"] is not None]; fl=[r["flip"] for r in s if r["flip"] is not None]
    print(f"  {lab:14s} fills={len(s):3d}  btc_vol med={st.median(bv) if bv else 0:.1f} mean={st.mean(bv) if bv else 0:.1f}  flip60 med={st.median(fl) if fl else 0:.2f}")
red=[r for r in tk if r["day"] in RED]; grn=[r for r in tk if r["day"] in GREEN]
print("=== regime axes: RED taker-days vs GREEN taker-days ===")
vstat(grn,"GREEN days"); vstat(red,"RED days")
print("\n=== taker win%/PnL by btc_vol (recent, gate is VOL_CAP=6.5) ===")
rec=[r for r in tk if r["day"] in RED|GREEN]
rep([r for r in rec if r["bvol"] is not None and r["bvol"]<5],"btc_vol <5")
rep([r for r in rec if r["bvol"] is not None and 5<=r["bvol"]<6.5],"btc_vol 5-6.5")
rep([r for r in rec if r["bvol"] is not None and 6.5<=r["bvol"]<9],"btc_vol 6.5-9 (gate skips entry)")
rep([r for r in rec if r["bvol"] is not None and r["bvol"]>=9],"btc_vol >=9")
print("\n=== RED-day losses: were they in the vol<6.5 (gate-proof) zone? ===")
rl=[r for r in red if not r["won"]]
rep([r for r in rl if r["bvol"] is not None and r["bvol"]<6.5],"red losses vol<6.5 (slipped gate)")
rep([r for r in rl if r["bvol"] is not None and r["bvol"]>=6.5],"red losses vol>=6.5")
print("\n=== same split for win%/PnL on RED vs GREEN within vol<6.5 (the traded zone) ===")
rep([r for r in grn if r["bvol"] is not None and r["bvol"]<6.5],"GREEN-day vol<6.5")
rep([r for r in red if r["bvol"] is not None and r["bvol"]<6.5],"RED-day vol<6.5")
print("\nREAD: if RED days have clearly higher btc_vol/flip -> a regime signature (tighten gate). If RED-day")
print("losses are mostly vol<6.5 (the zone we DO trade) and the regime axes look SAME as green -> it's the")
print("same gate-proof reversal story (no tradeable taker-regime signal beyond the existing vol cap).")
