"""ethpause_forgone.py — eth-pause skips eth when combined roll10>=2. How many WINS does it forgo vs LOSSES it
avoids? Net = avoided loss$ - forgone win$. Full sample + last 5d."""
import json, time
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
def load(f,keep):
    out=[]
    for o in (json.loads(l) for l in open(ROOT+"/"+f,encoding="utf-8") if l.strip()):
        if keep(o):
            w=ws_of(o.get("slug",""))
            if w and o.get("coin") in ("btc","eth"): out.append({"ws":w,"won":bool(o["won"]),"coin":o.get("coin"),"pnl":float(o.get("pnl",0) or 0)})
    return out
zm=load("data/multi_window_engine_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None)
tk=load("data/early_taker_probe.jsonl",lambda o:o.get("kind")=="entry" and o.get("won") is not None)
allf=sorted(zm+tk,key=lambda x:x["ws"])
def roll10(ws):
    s=[f for f in allf if f["ws"]<ws][-10:]
    return (sum(1 for f in s if not f["won"]) if len(s)>=10 else 0)
def report(t0,lab):
    skipped=[f for f in allf if f["coin"]=="eth" and f["ws"]>=t0 and roll10(f["ws"])>=2]  # what eth-pause skips
    wins=[f for f in skipped if f["won"]]; losses=[f for f in skipped if not f["won"]]
    eth_total=[f for f in allf if f["coin"]=="eth" and f["ws"]>=t0]
    ethwins=[f for f in eth_total if f["won"]]
    print(f"=== {lab} ===")
    print(f"  eth entries SKIPPED by pause (armed): {len(skipped)} of {len(eth_total)} eth fills ({len(skipped)/len(eth_total)*100:.0f}%)")
    print(f"    forgone WINS:  {len(wins):3d}  (${sum(f['pnl'] for f in wins):+7.2f})  = {len(wins)}/{len(ethwins)} of all eth wins suppressed = {len(wins)/len(ethwins)*100:.0f}%")
    print(f"    avoided LOSSES:{len(losses):3d}  (${sum(f['pnl'] for f in losses):+7.2f})")
    print(f"    NET (avoid loss - forgo win) = ${-sum(f['pnl'] for f in skipped):+.2f}")
    print(f"    avg forgone win = ${sum(f['pnl'] for f in wins)/len(wins) if wins else 0:+.2f}/win (small = armed-period 5sh)")
report(0,"FULL sample")
report(int(time.time())-5*86400,"last 5 days")
print("\nREAD: forgone wins are many in COUNT but tiny in $ (armed-period 5sh wins ~+$0.3); avoided losses are")
print("fewer but bigger (~-$4.5). Net positive because we skip a -EV bucket. Cost = giving up small wins.")
