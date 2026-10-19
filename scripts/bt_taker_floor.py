"""bt_taker_floor.py — should the taker stop buying the cheapest band (add a price FLOOR)? The right metric is
NOT loss rate (a 0.77 bet SHOULD lose ~23%) but EDGE = win% - avg_paid (does the band beat its implied prob?).
A floor only helps if the dropped band has NEGATIVE edge (win% < price). Real taker fills, + held-out split.
CAVEAT: in-sample; cheap band has flip-flopped historically ([[cheap-side-profits-favorite-band-loses]])."""
import json
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
tk=[]
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8") if l.strip()):
    if o.get("kind")=="entry" and o.get("won") is not None and o.get("paid") is not None:
        w=ws_of(o.get("slug",""))
        if w: tk.append({"ws":w,"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),"paid":float(o["paid"])})
tk.sort(key=lambda x:x["ws"])
def rep(s,lab):
    if not s: print(f"  {lab:22s} n=0"); return
    w=sum(1 for r in s if r["won"]); ap=sum(r["paid"] for r in s)/len(s); p=sum(r["pnl"] for r in s)
    edge=(w/len(s)-ap)*100   # win% minus implied prob, in pp
    print(f"  {lab:22s} n={len(s):3d} win%={w/len(s)*100:5.1f} avgPaid={ap:.3f} EDGE={edge:+5.1f}pp PnL=${p:+7.2f} $/n={p/len(s):+.3f}")
print("=== taker by price band: EDGE = win% - avgPaid (negative = overpaying = floor candidate) ===")
rep([r for r in tk if r["paid"]<0.78],"paid <0.78")
rep([r for r in tk if 0.78<=r["paid"]<0.80],"paid 0.78-0.80")
rep([r for r in tk if 0.80<=r["paid"]<0.85],"paid 0.80-0.85")
rep([r for r in tk if r["paid"]>=0.85],"paid >=0.85")
print("\n=== candidate floors: KEPT set vs ALL ===")
rep(tk,"ALL (no floor)")
rep([r for r in tk if r["paid"]>=0.78],"FLOOR >=0.78")
rep([r for r in tk if r["paid"]>=0.80],"FLOOR >=0.80")
print("  dropped sets:")
rep([r for r in tk if r["paid"]<0.78],"  dropped <0.78")
rep([r for r in tk if r["paid"]<0.80],"  dropped <0.80")
cut=tk[int(len(tk)*0.6)]["ws"]
print("\n=== HELD-OUT (last 40%): does the cheap band stay negative-edge? ===")
ho=[r for r in tk if r["ws"]>=cut]
rep([r for r in ho if r["paid"]<0.80],"HO dropped <0.80")
rep([r for r in ho if r["paid"]>=0.80],"HO kept >=0.80")
print("\nREAD: floor helps ONLY if dropped band edge is clearly NEGATIVE in BOTH full & held-out. If edge ~0")
print("(fairly priced) -> cutting it just removes breakeven volume (neutral); if edge>0 -> cutting HURTS.")
