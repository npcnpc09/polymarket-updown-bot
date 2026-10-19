"""regime_indicator_bt.py — FIRST CUT at a LEADING regime indicator (user-requested).
Hypothesis: the binance price path's own TREND-PERSISTENCE, measured AT WINDOW OPEN (before we enter,
independent of our outcomes), separates the favorable (trending, leads persist, we win) regime from the
unfavorable (choppy, leads reverse, we lose). Metric = Kaufman Efficiency Ratio over the prior 30 1m bars:
ER = |close_now - close_30ago| / sum|1m changes|.  ER->1 trend, ER->0 chop.
Tests: (1) per-trade win% by ER bucket (ER failed as an ENTRY gate before — expect weak); (2) REGIME-LEVEL:
daily mean ER vs daily win% (the new angle — does ER forecast the regime for SIZING?). Honest: characterize
in-hindsight is easy; this tests whether ER is computable-at-entry AND tracks the regime."""
import json, time, datetime, math, collections, urllib.request
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def load(fn,eng,pred):
    out=[]
    for l in open(ROOT+"/"+fn,encoding="utf-8"):
        if not l.strip(): continue
        try:o=json.loads(l)
        except:continue
        if pred(o):
            try: ws=int(o["slug"].rsplit("-",1)[1])
            except: continue
            out.append({"ws":ws,"coin":o.get("coin"),"won":bool(o["won"])})
    return out
fills=(load("data/multi_window_engine_live.jsonl","zm",lambda o:o.get("filled") is True and o.get("won") is not None)
      +load("data/early_taker_probe.jsonl","tk",lambda o:o.get("kind")=="entry" and o.get("won") is not None)
      +load("data/multi_window_engine_15m_live.jsonl","15m",lambda o:o.get("filled") is True and o.get("won") is not None))
fills=[f for f in fills if f["coin"] in ("btc","eth")]
lo=min(f["ws"] for f in fills)-2000; hi=max(f["ws"] for f in fills)+400
print(f"{len(fills)} btc/eth fills, ws range {lo}..{hi} ({(hi-lo)/86400:.1f} days)")
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
CACHE=ROOT+"/data/klines_cache.json"
try: kl=json.load(open(CACHE))
except: kl={}
def fetch(sym):
    if sym in kl and len(kl[sym])>100: return
    print(f"  fetching {sym} 1m klines...")
    out={}; start=lo*1000
    while start < hi*1000:
        url=f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1m&startTime={start}&limit=1000"
        try:
            d=json.load(urllib.request.urlopen(url,timeout=20))
        except Exception as e:
            print(f"    fetch err {e}"); break
        if not d: break
        for k in d: out[int(k[0])//60000]=float(k[4])  # minute-index -> close
        start=d[-1][0]+60000
        if len(d)<1000: break
    kl[sym]=out; print(f"    {sym}: {len(out)} bars")
for c in ("btc","eth"): fetch(SYM[c])
json.dump(kl,open(CACHE,"w"))
def er(sym,ws,n=30):
    m=ws//60; closes=[kl[sym].get(str(m-i)) or kl[sym].get(m-i) for i in range(n,-1,-1)]
    closes=[c for c in closes if c]
    if len(closes)<n//2+1: return None
    net=abs(closes[-1]-closes[0]); vol=sum(abs(closes[i]-closes[i-1]) for i in range(1,len(closes)))
    return net/vol if vol>0 else None
for f in fills: f["er"]=er(SYM[f["coin"]],f["ws"])
fe=[f for f in fills if f["er"] is not None]
print(f"\nER computed for {len(fe)}/{len(fills)} fills")
import statistics as st
W=[f for f in fe if f["won"]]; L=[f for f in fe if not f["won"]]
print(f"\n=== (1) per-trade: mean ER  win={st.mean([f['er'] for f in W]):.3f}  loss={st.mean([f['er'] for f in L]):.3f} ===")
print(f"  {'ER bucket':12s} {'n':>4s} {'win%':>6s}")
for lo_,hi_ in [(0,0.15),(0.15,0.25),(0.25,0.35),(0.35,0.5),(0.5,1.01)]:
    b=[f for f in fe if lo_<=f["er"]<hi_]
    if b: print(f"  {lo_:.2f}-{hi_:.2f}    {len(b):>4d} {sum(1 for f in b if f['won'])/len(b)*100:>5.0f}%")
print(f"\n=== (2) REGIME-LEVEL: daily mean ER vs daily win% (the key test) ===")
byday=collections.defaultdict(list)
for f in fe: byday[datetime.datetime.utcfromtimestamp(f["ws"]).strftime("%m-%d")].append(f)
rows=[]
print(f"  {'day':6s} {'n':>4s} {'win%':>6s} {'meanER':>7s}")
for d in sorted(byday):
    g=byday[d]; wr=sum(1 for f in g if f["won"])/len(g)*100; me=st.mean([f["er"] for f in g])
    rows.append((wr,me)); print(f"  {d:6s} {len(g):>4d} {wr:>5.0f}% {me:>7.3f}")
if len(rows)>3:
    n=len(rows); mw=st.mean([r[0] for r in rows]); me=st.mean([r[1] for r in rows])
    cov=sum((r[0]-mw)*(r[1]-me) for r in rows)/n; sw=st.pstdev([r[0] for r in rows]); se=st.pstdev([r[1] for r in rows])
    corr=cov/(sw*se) if sw*se>0 else 0
    print(f"\n  CORRELATION(daily win%, daily ER) = {corr:+.2f}  (n={n} days)")
    print("  >0.4 = ER tracks the regime (LEADING indicator candidate); ~0 = ER does NOT explain the regime")
