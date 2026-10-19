"""why_drawdown.py — anatomy of the 355->318 drawdown. Tally ALL settled trades (both 5m engines + 15m)
from around the $355 high (ws>=LO) to now: wins/losses, by size, coin, engine; biggest losses; net."""
import json
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
LO=1782113000  # ~ the $355.46 high
def load(fn,eng,pred):
    out=[]
    for l in open(ROOT+"/"+fn,encoding="utf-8"):
        if not l.strip(): continue
        try:o=json.loads(l)
        except:continue
        if pred(o):
            try: ws=int(o["slug"].rsplit("-",1)[1])
            except: continue
            if ws>=LO:
                sh=o.get("sh");
                out.append({"eng":eng,"ws":ws,"coin":o.get("coin"),"side":o.get("side"),
                            "won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),"sh":sh,
                            "B":o.get("B") or o.get("ask"),"z":o.get("zscore"),"vol":o.get("vol30"),
                            "roll":o.get("roll10"),"brk":o.get("breaker")})
    return out
zm=load("data/multi_window_engine_live.jsonl","zm",lambda o:o.get("filled") is True and o.get("won") is not None)
tk=load("data/early_taker_probe.jsonl","tk",lambda o:o.get("kind")=="entry" and o.get("won") is not None)
m15=load("data/multi_window_engine_15m_live.jsonl","15m",lambda o:o.get("filled") is True and o.get("won") is not None)
allt=sorted(zm+tk+m15,key=lambda x:x["ws"])
W=[t for t in allt if t["won"]]; L=[t for t in allt if not t["won"]]
print(f"=== since the $355 high (ws>={LO}): {len(allt)} settled trades ===")
print(f"  WINS  : {len(W):3d}  sum ${sum(t['pnl'] for t in W):+8.2f}")
print(f"  LOSSES: {len(L):3d}  sum ${sum(t['pnl'] for t in L):+8.2f}")
print(f"  NET   : ${sum(t['pnl'] for t in allt):+8.2f}   (win% {len(W)/max(1,len(allt))*100:.0f}%)")
print(f"\n=== losses by ENGINE ===")
for e in ("zm","tk","15m"):
    le=[t for t in L if t["eng"]==e]
    if le: print(f"  {e:4s}: {len(le):2d} losses, ${sum(t['pnl'] for t in le):+8.2f}")
print(f"\n=== losses by COIN ===")
for c in ("btc","eth","sol"):
    lc=[t for t in L if t["coin"]==c]
    if lc: print(f"  {c}: {len(lc):2d} losses, ${sum(t['pnl'] for t in lc):+8.2f}")
print(f"\n=== losses by SIZE (was the breaker containing?) ===")
big=[t for t in L if (t['sh'] or 0)>=15]; small=[t for t in L if 0<(t['sh'] or 0)<15]; none=[t for t in L if not t['sh']]
print(f"  20sh+ (full cell): {len(big):2d}, ${sum(t['pnl'] for t in big):+8.2f}  <- pre-breaker / un-downsized")
print(f"  <15sh (5sh/taker): {len(small)+len(none):2d}, ${sum(t['pnl'] for t in (small+none)):+8.2f}  <- breaker-contained / small")
print(f"\n=== the 5 biggest single losses ===")
for t in sorted(L,key=lambda x:x['pnl'])[:5]:
    print(f"  {t['eng']:3s} {t['coin']} {t['side']} {t['sh']}sh @{t['B']} z={t['z']} vol={t['vol']} roll10={t['roll']} -> ${t['pnl']:+.2f}")
# clustering: losses in time order
print(f"\n=== loss timeline (gaps show clustering) — ws delta from high, coin, $, roll10 ===")
for t in L:
    print(f"  +{(t['ws']-LO)//60:4d}min {t['eng']:3s} {t['coin']:3s} {str(t['sh']):>3}sh ${t['pnl']:+6.2f} roll10={t['roll']}")
