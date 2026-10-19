"""bt_cell_loss_chop.py — do the REAL cell losses (esp. the 20sh air-pockets) have CHOPPIER pre-entry paths than
the cell wins? For each cell fill in the last ~5.5d (binance 1s available), reconstruct the min0->min3 1s path,
compute the 10s-bucketed sign-flip count, and compare losses vs wins + the air-pockets specifically."""
import httpx, math, statistics as st, time
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
import json
SYM={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT"}
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
cutoff=int(time.time())-int(5.6*86400)
cell=[]
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl",encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None and o.get("B") and 0.90<=o["B"]<0.96:
        w=ws_of(o.get("slug",""))
        if w and w>=cutoff and o.get("coin") in SYM:
            cell.append({"ws":w,"coin":o["coin"],"won":bool(o["won"]),"sh":int(o.get("sh",5)),"B":o["B"]})
cell.sort(key=lambda x:x["ws"])
c=httpx.Client(timeout=15,headers={"User-Agent":"x"})
def preentry_flips(coin,ws):
    try:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1s","startTime":ws*1000,"endTime":(ws+185)*1000,"limit":200}).json()
    except: return None
    if not isinstance(k,list) or len(k)<150: return None
    P={r[0]//1000-ws:float(r[4]) for r in k}
    seq=[P.get(s) for s in range(0,181,10)]; seq=[x for x in seq if x is not None]
    if len(seq)<12: return None
    r=[seq[i]-seq[i-1] for i in range(1,len(seq))]; sg=[1 if x>=0 else -1 for x in r]
    return sum(1 for i in range(1,len(sg)) if sg[i]!=sg[i-1])
for x in cell:
    x["flips"]=preentry_flips(x["coin"],x["ws"])
got=[x for x in cell if x["flips"] is not None]
W=[x for x in got if x["won"]]; L=[x for x in got if not x["won"]]
print(f"cell fills in window: {len(cell)}, 1s-reconstructed: {len(got)}  (wins {len(W)}, losses {len(L)})")
if W: print(f"\n  WINS   avg pre-entry flips = {st.mean([x['flips'] for x in W]):.2f}  median {sorted(x['flips'] for x in W)[len(W)//2]}")
if L: print(f"  LOSSES avg pre-entry flips = {st.mean([x['flips'] for x in L]):.2f}  median {sorted(x['flips'] for x in L)[len(L)//2]}")
print(f"\n  === each cell LOSS: pre-entry flips ===")
from datetime import datetime,timezone
for x in L:
    t=datetime.fromtimestamp(x["ws"],timezone.utc).strftime("%m-%d %H:%M")
    tag=" <-- 20sh AIR-POCKET" if x["sh"]>=20 else ""
    print(f"    {t} {x['coin']} B={x['B']} sh={x['sh']} flips={x['flips']}{tag}")
# win-rate by flip bucket within this sample
def rep(s,lab):
    if not s: print(f"    {lab:16s} n=0"); return
    w=sum(1 for x in s if x["won"]); print(f"    {lab:16s} n={len(s):3d} win%={w/len(s)*100:5.1f}")
print(f"\n  === cell win% by pre-entry flips (this sample) ===")
rep([x for x in got if x["flips"]<=6],"clean <=6")
rep([x for x in got if 7<=x["flips"]<=9],"medium 7-9")
rep([x for x in got if x["flips"]>=10],"choppy >=10")
print("\nREAD: hypothesis holds if LOSSES (esp. air-pockets) have clearly HIGHER pre-entry flips than wins.")
print("If air-pockets are LOW-flip (clean path that still reversed) -> pre-entry chop does NOT catch them.")
