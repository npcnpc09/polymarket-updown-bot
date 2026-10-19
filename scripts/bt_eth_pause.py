"""bt_eth_pause.py — user's rule: when the COMBINED breaker is armed (bad regime, the validated detector since
btc leads eth), PAUSE eth (cell+taker), keep btc running; resume eth when combined disarms ('eth回转'). Test:
(1) is eth -EV when armed (so skipping helps)? (2) is btc still OK when armed (so keep it)? (3) policy PnL impact."""
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
                sh=float(o.get("sh",5) or 5); B=float(o.get("B") or o.get("paid") or 0.8)
                out.append({"ws":w,"coin":o["coin"],"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),"risk":sh*B})
    return out
zm=load("data/multi_window_engine_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None)
tk=load("data/early_taker_probe.jsonl",lambda o:o.get("kind")=="entry" and o.get("won") is not None)
allf=sorted(zm+tk,key=lambda x:x["ws"])  # combined stream
def roll10(ws):
    s=[f for f in allf if f["ws"]<ws][-10:]
    return (sum(1 for f in s if not f["won"]) if len(s)>=10 else 0)
for f in allf: f["armed"]=(roll10(f["ws"])>=2)
def rep(s,lab):
    if not s: print(f"  {lab:28s} n=0"); return
    w=sum(1 for r in s if r["won"]); p=sum(r["pnl"] for r in s); risk=sum(r["risk"] for r in s)
    print(f"  {lab:28s} n={len(s):4d} win%={w/len(s)*100:5.1f} PnL=${p:+8.2f} G={p/risk*100 if risk else 0:+.2f}%")
print("=== (1) eth: armed vs calm (is eth -EV when combined armed?) ===")
rep([f for f in allf if f["coin"]=="eth" and not f["armed"]],"eth CALM (roll10<2)")
rep([f for f in allf if f["coin"]=="eth" and f["armed"]],"eth ARMED (roll10>=2)")
print("\n=== (2) btc: armed vs calm (is btc still OK when armed = keep it?) ===")
rep([f for f in allf if f["coin"]=="btc" and not f["armed"]],"btc CALM")
rep([f for f in allf if f["coin"]=="btc" and f["armed"]],"btc ARMED")
print("\n=== (3) policy impact: skip eth when armed ===")
cur=sum(f["pnl"] for f in allf)
eth_armed_pnl=sum(f["pnl"] for f in allf if f["coin"]=="eth" and f["armed"])
print(f"  CURRENT total PnL (btc+eth)        = ${cur:+.2f}")
print(f"  eth fills WHEN ARMED contributed   = ${eth_armed_pnl:+.2f}  (skipping them changes PnL by ${-eth_armed_pnl:+.2f})")
print(f"  USER RULE total (skip eth-armed)   = ${cur-eth_armed_pnl:+.2f}")
# held-out
cut=allf[int(len(allf)*0.6)]["ws"]
ho=[f for f in allf if f["ws"]>=cut]
hocur=sum(f["pnl"] for f in ho); hoeth=sum(f["pnl"] for f in ho if f["coin"]=="eth" and f["armed"])
print(f"\n  HELD-OUT: current ${hocur:+.2f} -> skip-eth-armed ${hocur-hoeth:+.2f} (delta ${-hoeth:+.2f})")
print("\nREAD: deploy iff eth-ARMED G is clearly negative (skipping it is +EV) in full AND held-out, AND btc-ARMED")
print("is still positive (so we correctly keep btc). If eth-armed is ~breakeven -> skipping just cuts volume.")
