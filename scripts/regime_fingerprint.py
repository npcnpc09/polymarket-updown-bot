"""regime_fingerprint.py — DESCRIPTIVE (not predictive) summary: what distinguishes a FAVORABLE period for us
(06-09->13, +$198, 91-win streak) from an UNFAVORABLE/plateau one (06-15->20)? Compute a full indicator panel,
MARKET-side and OUTCOME-side, side by side. Uses full-period data incl. settles (descriptive is allowed to)."""
import httpx, math, statistics as st, json, time
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
COINS={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT"}
FAV=(1780963200,1781308800)   # 06-09 -> 06-13
UNF=(1781481600,1781942000)   # 06-15 -> 06-20
def klines_1m(sym,t0,t1):
    out=[]; t=t0
    with httpx.Client(timeout=25) as c:
        while t<t1:
            try: k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":t*1000,"endTime":t1*1000,"limit":1000}).json()
            except: time.sleep(1); continue
            if not isinstance(k,list) or not k: break
            for r in k: out.append((r[0]//1000,float(r[1]),float(r[4])))
            t=k[-1][0]//1000+60
            if len(k)<1000: break
    return out
# market-side: btc vol/flip/ER + all-coin settle-margin distribution
def market(t0,t1):
    kb=klines_1m("BTCUSDT",t0,t1); closes=[x[2] for x in kb]
    rets=[math.log(closes[i]/closes[i-1])*1e4 for i in range(1,len(closes))]
    vol=st.pstdev(rets); sg=[1 if r>=0 else -1 for r in rets]
    flip=sum(1 for i in range(1,len(sg)) if sg[i]!=sg[i-1])/(len(sg)-1)
    er=abs(sum(rets))/sum(abs(r) for r in rets)
    margins=[]
    for coin,sym in COINS.items():
        k=klines_1m(sym,t0,t1); O={t:o for t,o,c in k}; C={t:c for t,o,c in k}
        t=t0-(t0%300)
        while t+300<=t1:
            op=O.get(t); cl=C.get(t+300) or O.get(t+300)
            if op and cl: margins.append(abs(math.log(cl/op)*1e4))
            t+=300
    margins.sort()
    return vol,flip,er,st.median(margins),sum(1 for m in margins if m<5)/len(margins)
# outcome-side: our fills
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
            if w: fills.append({"ws":w,"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),"cell":(o.get("B") and 0.90<=o["B"]<0.96)})
def runs_z(seq):
    n1=sum(seq); n0=len(seq)-n1
    if n1==0 or n0==0: return 0
    runs=1+sum(1 for i in range(1,len(seq)) if seq[i]!=seq[i-1])
    mu=2*n1*n0/(n1+n0)+1; var=(mu-1)*(mu-2)/(n1+n0-1)
    return (runs-mu)/(var**0.5) if var>0 else 0
def outcome(t0,t1):
    s=[f for f in fills if t0<=f["ws"]<t1]; s.sort(key=lambda x:x["ws"])
    if not s: return None
    w=sum(1 for f in s if f["won"])/len(s)
    cell=[f for f in s if f["cell"]]; cw=sum(1 for f in cell if f["won"])/len(cell) if cell else 0
    seq=[1 if f["won"] else 0 for f in s]
    return len(s),w,cw,runs_z(seq),sum(f["pnl"] for f in s)
print(f"{'INDICATOR':30s} {'FAVORABLE(06-09->13)':>22s} {'UNFAVORABLE(06-15->20)':>23s}")
print("-"*78)
for lab,rng in (("",FAV),):  pass
mf=market(*FAV); mu=market(*UNF)
print("--- MARKET-SIDE (price) ---")
print(f"{'btc 1m vol (bps)':30s} {mf[0]:>22.1f} {mu[0]:>23.1f}")
print(f"{'btc flip-rate':30s} {mf[1]:>22.2f} {mu[1]:>23.2f}")
print(f"{'btc efficiency-ratio':30s} {mf[2]:>22.3f} {mu[2]:>23.3f}")
print(f"{'median settle-margin (bps)':30s} {mf[3]:>22.1f} {mu[3]:>23.1f}")
print(f"{'tight-settle rate (<5bps)':30s} {mf[4]*100:>21.0f}% {mu[4]*100:>22.0f}%")
of=outcome(*FAV); ou=outcome(*UNF)
print("--- OUTCOME-SIDE (our fills) ---")
print(f"{'our fills':30s} {of[0]:>22d} {ou[0]:>23d}")
print(f"{'our win%':30s} {of[1]*100:>21.1f}% {ou[1]*100:>22.1f}%")
print(f"{'our CELL win%':30s} {of[2]*100:>21.1f}% {ou[2]*100:>22.1f}%")
print(f"{'loss-clustering runs-z':30s} {of[3]:>22.2f} {ou[3]:>23.2f}")
print(f"{'period PnL':30s} {('$%+.0f'%of[4]):>22s} {('$%+.0f'%ou[4]):>23s}")
print("\nREAD: indicators that DIFFER = the descriptive fingerprint of 顺 vs 不顺. Expect market-side ~same")
print("(proven), outcome-side to separate. The honest summary = which dashboard actually distinguishes them.")
