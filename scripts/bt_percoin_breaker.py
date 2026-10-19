"""bt_percoin_breaker.py — PER-COIN breaker vs current COMBINED breaker. For each cell fill, size by roll10 of:
  (A) COMBINED stream (btc+eth taker+zmaker) = current deployed
  (B) PER-COIN stream (that coin's own taker+zmaker)
Sizing: roll10>=2 ->5sh, ==0 ->28sh, else 20sh. Recompute cell PnL/G. Tests if per-coin avoids 'btc cell
downsized because eth dragged combined' + de-risks eth specifically. Held-out included."""
import json
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
def load(f,keep):
    out=[]
    for o in (json.loads(l) for l in open(ROOT+"/"+f,encoding="utf-8") if l.strip()):
        if keep(o):
            w=ws_of(o.get("slug",""))
            if w and o.get("coin") in ("btc","eth"):
                out.append({"ws":w,"coin":o["coin"],"won":bool(o["won"]),"B":o.get("B")})
    return out
zm=load("data/multi_window_engine_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None)
tk=load("data/early_taker_probe.jsonl",lambda o:o.get("kind")=="entry" and o.get("won") is not None)
allf=sorted(zm+tk,key=lambda x:x["ws"])
cells=sorted([f for f in zm if f["B"] and 0.90<=f["B"]<0.96],key=lambda x:x["ws"])
def roll10(stream,ws):
    s=[f for f in stream if f["ws"]<ws][-10:]
    return (sum(1 for f in s if not f["won"]) if len(s)>=10 else None)
def size(r):
    if r is None: return 20
    if r>=2: return 5
    if r==0: return 28
    return 20
def pnl(sh,won,B): return sh*(1-B) if won else -sh*B
def evaluate(sub,lab):
    cp=0.0; pp=0.0; cr=0.0; pr=0.0; diff=[]
    for c in sub:
        rc=roll10(allf,c["ws"])                                  # combined
        rp=roll10([f for f in allf if f["coin"]==c["coin"]],c["ws"])  # per-coin
        sc=size(rc); sp=size(rp)
        cp+=pnl(sc,c["won"],c["B"]); cr+=sc*c["B"]
        pp+=pnl(sp,c["won"],c["B"]); pr+=sp*c["B"]
    print(f"  {lab}:")
    print(f"    COMBINED (current) PnL=${cp:+8.2f} risk=${cr:6.0f} G={cp/cr*100 if cr else 0:+.2f}%")
    print(f"    PER-COIN           PnL=${pp:+8.2f} risk=${pr:6.0f} G={pp/pr*100 if pr else 0:+.2f}%")
print(f"cell fills {len(cells)} | combined stream {len(allf)}")
print("\n=== FULL period ===")
evaluate(cells,"ALL")
evaluate([c for c in cells if c["coin"]=="btc"],"btc cells")
evaluate([c for c in cells if c["coin"]=="eth"],"eth cells")
cut=cells[int(len(cells)*0.6)]["ws"]
print("\n=== HELD-OUT (last 40%) ===")
evaluate([c for c in cells if c["ws"]>=cut],"held-out ALL")
print("\nREAD: per-coin wins if its G >= combined (esp. on btc cells, where per-coin avoids eth-dragged downsizing,")
print("and overall). If per-coin G < combined -> the sparser per-coin stream's slower detection costs more than")
print("the divergence-specificity gains (the density argument wins).")
