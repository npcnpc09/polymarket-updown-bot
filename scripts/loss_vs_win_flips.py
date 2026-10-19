"""loss_vs_win_flips.py — direct test of 'losing windows have visibly more reversals'. For our fills since the
$330 peak, reconstruct each window's 1s path, count within-window direction flips (10s-bucketed), compare the
LOSS windows vs the WIN windows. If losers clearly choppier -> a visible signal exists. If same -> reversals
are everywhere (the eye is fooled by hindsight)."""
import httpx, math, statistics as st, json, time
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
SYM={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT"}
PEAK=1781971010
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
fills=[]
for f,keep in (("data/multi_window_engine_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None),
               ("data/early_taker_probe.jsonl",lambda o:o.get("kind")=="entry" and o.get("won") is not None),
               ("data/multi_window_engine_sol_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None)):
    for o in (json.loads(l) for l in open(ROOT+"/"+f,encoding="utf-8") if l.strip()):
        if keep(o):
            w=ws_of(o.get("slug",""))
            if w and w>=PEAK-300 and o.get("coin") in SYM:
                fills.append({"ws":w,"coin":o["coin"],"won":bool(o["won"])})
# dedupe by (coin,ws) keep one
seen={}
for x in fills: seen[(x["coin"],x["ws"])]=x
fills=list(seen.values())
c=httpx.Client(timeout=15,headers={"User-Agent":"x"})
def flips(coin,ws):
    try:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1s","startTime":ws*1000,"endTime":(ws+300)*1000,"limit":320}).json()
    except: return None
    if not isinstance(k,list) or len(k)<250: return None
    P={r[0]//1000-ws:float(r[4]) for r in k}
    seq=[P.get(s) for s in range(0,300,10)]; seq=[x for x in seq if x is not None]
    if len(seq)<25: return None
    r=[seq[i]-seq[i-1] for i in range(1,len(seq))]; sg=[1 if x>=0 else -1 for x in r]
    return sum(1 for i in range(1,len(sg)) if sg[i]!=sg[i-1])
for x in fills: x["flips"]=flips(x["coin"],x["ws"])
got=[x for x in fills if x["flips"] is not None]
L=[x["flips"] for x in got if not x["won"]]; W=[x["flips"] for x in got if x["won"]]
print(f"windows since peak: {len(got)} reconstructed (losses {len(L)}, wins {len(W)})")
print(f"  (max possible flips in a 5m window @10s buckets ~ 29)\n")
if L: print(f"  LOSS windows: flips median={st.median(L):.0f} mean={st.mean(L):.1f} range {min(L)}-{max(L)}")
if W: print(f"  WIN  windows: flips median={st.median(W):.0f} mean={st.mean(W):.1f} range {min(W)}-{max(W)}")
print("\n  each LOSS window's flip count:")
for x in sorted([g for g in got if not g["won"]],key=lambda z:-z["flips"]):
    from datetime import datetime,timezone
    print(f"    {datetime.fromtimestamp(x['ws'],timezone.utc).strftime('%m-%d %H:%M')} {x['coin']} flips={x['flips']}")
print("\nREAD: if LOSS median flips >> WIN median -> losing windows ARE visibly choppier (a real signal).")
print("If LOSS ≈ WIN -> the reversals are in winning windows too; 'so many reversals' is hindsight, not separable.")
