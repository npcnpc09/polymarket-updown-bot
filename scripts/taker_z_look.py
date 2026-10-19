"""taker_z_look.py — DESCRIPTIVE look (in-sample): split the LIVE taker fills by z=|lead|/coin_vol30
and by coin_vol30, to SEE if the eth bleed is low-z / high-vol. NOT a validated gate (same fills that
flagged it -> in-sample). Decide an INDEPENDENT backtest after."""
import json, collections
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
rows = []
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl", encoding="utf-8") if l.strip()):
    if o.get("kind")=="entry" and o.get("won") is not None:
        rows.append({"coin":o.get("coin"),"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),
                     "z":o.get("zscore"),"cvol":o.get("coin_vol30"),"bvol":o.get("btc_vol"),
                     "lead":abs(o.get("lead2") or o.get("lead") or 0),"B":o.get("paid") or o.get("B")})
nz = [r for r in rows if r["z"] is not None]
print(f"total taker fills {len(rows)}; with z logged {len(nz)} (z added recently)")
def rep(s, lab):
    if not s: print(f"  {lab:20s} n=0"); return
    w=sum(1 for r in s if r["won"]); p=sum(r["pnl"] for r in s)
    print(f"  {lab:20s} n={len(s):3d} win%={w/len(s)*100:5.1f} PnL=${p:+8.2f} avg${p/len(s):+.2f}")
print("\n=== by z bucket (all coins, z-logged fills) ===")
rep([r for r in nz if r["z"]<1.5], "z<1.5")
rep([r for r in nz if 1.5<=r["z"]<2.0], "z 1.5-2.0")
rep([r for r in nz if 2.0<=r["z"]<2.5], "z 2.0-2.5")
rep([r for r in nz if r["z"]>=2.5], "z>=2.5")
for coin in ("eth","btc"):
    cz = [r for r in nz if r["coin"]==coin]
    print(f"\n=== {coin} by z bucket (n={len(cz)}) ===")
    rep([r for r in cz if r["z"]<2.0], f"{coin} z<2.0")
    rep([r for r in cz if 2.0<=r["z"]<2.5], f"{coin} z 2.0-2.5")
    rep([r for r in cz if r["z"]>=2.5], f"{coin} z>=2.5")
print("\n=== z-gate candidate: KEEP z>=2.5 vs ALL (z-logged fills only) ===")
rep(nz, "ALL (no z gate)")
rep([r for r in nz if r["z"]>=2.5], "GATE z>=2.5")
rep([r for r in nz if r["z"]>=2.0], "GATE z>=2.0")
print("\n=== by coin_vol30 (per-coin vol, separate from btc_vol cap) ===")
ncv=[r for r in rows if r["cvol"] is not None]
rep([r for r in ncv if r["cvol"]<5], "cvol<5")
rep([r for r in ncv if 5<=r["cvol"]<8], "cvol 5-8")
rep([r for r in ncv if r["cvol"]>=8], "cvol>=8")
print("\nNOTE: IN-SAMPLE (these fills flagged the pattern). A real z-gate needs an INDEPENDENT backtest")
print("(z>=2.5 was OOS-validated for the MAKER; taker never gated on z). Burden of proof = held-out slice.")
