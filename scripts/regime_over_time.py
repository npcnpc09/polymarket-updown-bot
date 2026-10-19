"""regime_over_time.py — is our edge REGIME-CONDITIONAL? Bucket our real fills by day; show win% and
net PnL per day across the 16-day arc. If win% was high during the growth period and dropped during the
plateau, the regime shifted (trending->choppy) and the edge is conditional, NOT a constant thin edge.
Also a market-side reversal proxy: of our settled directional bets, the LOSS RATE = how often the lead
we followed reversed by settle = the choppiness of the regime."""
import json, datetime, collections
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def day(ws): return datetime.datetime.utcfromtimestamp(ws).strftime("%m-%d")
def load(fn,eng,pred):
    out=[]
    for l in open(ROOT+"/"+fn,encoding="utf-8"):
        if not l.strip(): continue
        try:o=json.loads(l)
        except:continue
        if pred(o):
            try: ws=int(o["slug"].rsplit("-",1)[1])
            except: continue
            out.append({"ws":ws,"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),"coin":o.get("coin")})
    return out
zm=load("data/multi_window_engine_live.jsonl","zm",lambda o:o.get("filled") is True and o.get("won") is not None)
tk=load("data/early_taker_probe.jsonl","tk",lambda o:o.get("kind")=="entry" and o.get("won") is not None)
m15=load("data/multi_window_engine_15m_live.jsonl","15m",lambda o:o.get("filled") is True and o.get("won") is not None)
allt=zm+tk+m15
byday=collections.defaultdict(list)
for t in allt: byday[day(t["ws"])].append(t)
print(f"=== per-day: win% and net (all engines, {len(allt)} fills) ===")
print(f"  {'day':6s} {'n':>4s} {'win%':>6s} {'net$':>9s} {'lossRate(reversal%)':>20s}")
for d in sorted(byday):
    g=byday[d]; n=len(g); w=sum(1 for t in g if t["won"]); net=sum(t["pnl"] for t in g)
    print(f"  {d:6s} {n:>4d} {w/n*100:>5.0f}% {net:>+9.2f} {(n-w)/n*100:>19.0f}%")
# split: first third (growth) vs last third (plateau)
allt_s=sorted(allt,key=lambda x:x["ws"]); k=len(allt_s)//3
early=allt_s[:k]; late=allt_s[-k:]
def stat(s):
    n=len(s); w=sum(1 for t in s if t["won"]); return n,w/n*100,sum(t["pnl"] for t in s),(n-w)/n*100
for lab,s in [("EARLY third (growth)",early),("LATE third (plateau)",late)]:
    n,wp,net,lr=stat(s)
    print(f"\n  {lab}: n={n} win%={wp:.1f} net=${net:+.2f} reversal/lossRate={lr:.1f}%")
