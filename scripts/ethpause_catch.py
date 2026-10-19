"""ethpause_catch.py — would the deployed eth-pause (skip eth when combined roll10>=2) have caught the recent
eth losses? Split recent eth losses by roll10 at the time: >=2 = CAUGHT (eth-pause skips), <2 = MISSED
(pre-detection, the unavoidable head of each cluster). Shows the catch depends on cluster length."""
import json
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
import time
cut=int(time.time())-5*86400
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
# reconstruct combined roll10 for every eth loss
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
eth_losses=[f for f in allf if f["coin"]=="eth" and not f["won"] and f["ws"]>=cut]
caught=[f for f in eth_losses if roll10(f["ws"])>=2]
missed=[f for f in eth_losses if roll10(f["ws"])<2]
from datetime import datetime,timezone
print(f"recent eth losses (last 5d): {len(eth_losses)}, total ${sum(f['pnl'] for f in eth_losses):+.2f}\n")
print(f"  CAUGHT by eth-pause (roll10>=2): {len(caught)} losses, ${sum(f['pnl'] for f in caught):+.2f}")
print(f"  MISSED (roll10<2, pre-detection): {len(missed)} losses, ${sum(f['pnl'] for f in missed):+.2f}")
print(f"\n  -> eth-pause catches {len(caught)}/{len(eth_losses)} = {len(caught)/len(eth_losses)*100:.0f}% of recent eth losses, ${sum(f['pnl'] for f in caught):+.2f} of ${sum(f['pnl'] for f in eth_losses):+.2f}")
print("\nREAD: eth-pause catches the TAIL of each loss cluster (after roll10>=2), not the HEAD (first ~2 losses")
print("that ARM it). Long clusters -> catches most; short 2-3 clusters -> catches little. The head is the")
print("irreducible change-point cost (no signal until the first losses reveal the bad phase).")
