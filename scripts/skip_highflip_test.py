"""skip_highflip_test.py — would skipping high-flip windows help? Two parts:
(A) on the recent 54-window sample: win% by FULL-window flip bucket (does high-flip lose more?). CAVEAT: full-
    window flips are only knowable AFTER settle = NOT actionable at entry.
(B) the ACTIONABLE version (pre-entry flips, knowable at entry) was already tested big-sample + held-out in
    bt_preentry_chop_big.py and FAILED (held-out flipped). This re-states that verdict."""
import httpx, json, statistics as st
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
            if w and w>=PEAK-300 and o.get("coin") in SYM: fills.append({"ws":w,"coin":o["coin"],"won":bool(o["won"])})
seen={}
for x in fills: seen[(x["coin"],x["ws"])]=x
fills=list(seen.values())
c=httpx.Client(timeout=15,headers={"User-Agent":"x"})
def flips(coin,ws):
    try: k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1s","startTime":ws*1000,"endTime":(ws+300)*1000,"limit":320}).json()
    except: return None
    if not isinstance(k,list) or len(k)<250: return None
    P={r[0]//1000-ws:float(r[4]) for r in k}; seq=[P.get(s) for s in range(0,300,10)]; seq=[x for x in seq if x is not None]
    if len(seq)<25: return None
    r=[seq[i]-seq[i-1] for i in range(1,len(seq))]; sg=[1 if x>=0 else -1 for x in r]
    return sum(1 for i in range(1,len(sg)) if sg[i]!=sg[i-1])
for x in fills: x["flips"]=flips(x["coin"],x["ws"])
got=[x for x in fills if x["flips"] is not None]
def wr(s):
    return f"n={len(s):2d} win%={sum(1 for x in s if x['won'])/len(s)*100:4.0f}" if s else "n=0"
print(f"(A) recent {len(got)} windows, win% by FULL-window flips (NOT knowable at entry):")
for lo,hi,lab in ((0,12,"<12"),(12,14,"12-13"),(14,99,">=14")):
    print(f"   flips {lab:6s}: {wr([x for x in got if lo<=x['flips']<hi])}")
print(f"\n   candidate 'skip >=14 flips': KEEP {wr([x for x in got if x['flips']<14])} | SKIP {wr([x for x in got if x['flips']>=14])}")
print("\n(B) ACTIONABLE version (pre-entry flips, knowable at entry) = bt_preentry_chop_big.py verdict:")
print("    FULL: clean<=6 98.7% vs rest 97.8% (spread 0.9pp). HELD-OUT: clean 98.9% vs rest 99.3% -> FLIPPED.")
print("    => pre-entry flip-skip REFUTED OOS. Full-window flips aren't actionable. Either way, skipping fails.")
