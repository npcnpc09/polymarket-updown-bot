"""eth_current_phase.py — is ETH CURRENTLY in a phase that suits our strategy? Read it from OUR OUTCOMES (the
only valid lens; price proven useless). Rolling G + win% for eth vs btc over recent windows. Also: per-coin
loss-clustering (would a PER-COIN breaker de-risk eth specifically when eth is bad?)."""
import json, time
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
now=int(time.time())
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
fills=[]
for f,keep in (("data/multi_window_engine_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None),
               ("data/early_taker_probe.jsonl",lambda o:o.get("kind")=="entry" and o.get("won") is not None)):
    for o in (json.loads(l) for l in open(ROOT+"/"+f,encoding="utf-8") if l.strip()):
        if keep(o):
            w=ws_of(o.get("slug",""))
            if w and o.get("coin") in ("btc","eth"):
                sh=float(o.get("sh",5) or 5); B=float(o.get("B") or o.get("paid") or 0.8)
                fills.append({"ws":w,"coin":o["coin"],"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),"risk":sh*B})
def g(s):
    if not s: return (0,0,0)
    p=sum(x["pnl"] for x in s); r=sum(x["risk"] for x in s); w=sum(1 for x in s if x["won"])/len(s)*100
    return len(s),w,(p/r*100 if r else 0)
def show(coin,t0,lab):
    s=[x for x in fills if x["coin"]==coin and x["ws"]>=t0]
    n,w,G=g(s); print(f"    {coin} {lab:10s}: n={n:3d} win%={w:5.1f} G={G:+5.2f}%")
print("=== eth vs btc realized G, recent windows (OUR OUTCOMES = the valid lens) ===")
for lab,h in (("last 12h",12),("last 24h",24),("last 48h",48),("last 4d",96)):
    print(f"  {lab}:")
    show("btc",now-h*3600,lab); show("eth",now-h*3600,lab)
# per-coin recent loss streak (the breaker read, per coin)
print("\n=== last 12 fills per coin (recent loss clustering) ===")
for coin in ("btc","eth"):
    s=sorted([x for x in fills if x["coin"]==coin],key=lambda x:x["ws"])[-12:]
    seq="".join("W" if x["won"] else "L" for x in s)
    print(f"  {coin}: {seq}  ({seq.count('L')} losses in last {len(s)})")
print("\nREAD: if eth's recent G is clearly negative while btc's is positive -> eth IS currently in an unsuitable")
print("phase BY OUR OUTCOMES (not price). That's the only honest 'is eth suited now' signal. A per-coin breaker")
print("could de-risk eth specifically -- but per-coin stream is sparser (slower detection); tradeoff to test.")
