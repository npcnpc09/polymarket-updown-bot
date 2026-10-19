"""bt_tightcall_density.py — TEST the theory: ε^oracle loss-RATE ∝ tight-call settle density (windows settling
near the strike = Chainlink coin-flips). Compute per 5m window (btc/eth/sol) the settle margin |log(close/open)|;
tight if < TAU bps. Density_t = fraction of all-coin windows in prior 30min that were tight (dense, binance-
observable). Test: does high prior tight-density predict our CELL losses? Compare its lift to the breaker.
Theory: tight-density is the dense binance-observable that loads on the ε-rate mechanism (decision-boundary
quantization) -> may predict/lead better than the sparse outcome breaker."""
import httpx, math, statistics as st, json, time
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
COINS={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT"}; TAU=5.0
now=int(time.time()); start=now-8*86400
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
# build per-window settle margin (all coins), as a time series of (settle_time, is_tight)
windows=[]
for coin,sym in COINS.items():
    k=klines_1m(sym,start,now); O={t:o for t,o,c in k}; C={t:c for t,o,c in k}
    t=start-(start%300)
    while t+300<=now:
        op=O.get(t); cl=C.get(t+300) or O.get(t+300)
        if op and cl:
            margin=abs(math.log(cl/op)*1e4)
            windows.append({"settle":t+300,"tight":margin<TAU})
        t+=300
windows.sort(key=lambda x:x["settle"])
def tight_density(ws):  # fraction tight among all-coin windows settling in prior 30min
    s=[w for w in windows if ws-1800<=w["settle"]<ws]
    if len(s)<6: return None
    return sum(1 for w in s if w["tight"])/len(s)
# our cell fills + breaker stream
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
zm=[]; comb=[]
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl",encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None:
        w=ws_of(o.get("slug",""))
        if w: zm.append({"ws":w,"won":bool(o["won"]),"B":o.get("B")}); comb.append({"ws":w,"won":bool(o["won"])})
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8") if l.strip()):
    if o.get("kind")=="entry" and o.get("won") is not None:
        w=ws_of(o.get("slug",""))
        if w: comb.append({"ws":w,"won":bool(o["won"])})
comb.sort(key=lambda x:x["ws"])
cells=sorted([f for f in zm if f["B"] and 0.90<=f["B"]<0.96],key=lambda x:x["ws"])
def roll(ws):
    s=[f for f in comb if f["ws"]<ws][-10:]
    return (sum(1 for f in s if not f["won"]) if len(s)>=10 else None)
rows=[]
for c in cells:
    td=tight_density(c["ws"]); rl=roll(c["ws"])
    if td is None: continue
    rows.append({"won":c["won"],"td":td,"armed":(rl is not None and rl>=2)})
print(f"cell fills with tight-density: {len(rows)} | TAU={TAU}bps | overall tight rate {sum(1 for w in windows if w['tight'])/len(windows)*100:.0f}%")
def lr(s): return sum(1 for r in s if not r["won"])/len(s)*100 if s else 0
tds=sorted(r["td"] for r in rows); q1,q2=tds[len(tds)//3],tds[2*len(tds)//3]
print(f"\n=== cell-loss% by prior tight-call density (terciles: low<{q1:.2f}, high>{q2:.2f}) ===")
print(f"  low  td<{q1:.2f}: n={len([r for r in rows if r['td']<q1]):3d} cell-loss%={lr([r for r in rows if r['td']<q1]):4.1f}")
print(f"  med         : n={len([r for r in rows if q1<=r['td']<q2]):3d} cell-loss%={lr([r for r in rows if q1<=r['td']<q2]):4.1f}")
print(f"  high td>{q2:.2f}: n={len([r for r in rows if r['td']>=q2]):3d} cell-loss%={lr([r for r in rows if r['td']>=q2]):4.1f}")
print(f"\n=== vs breaker (combined roll10>=2) ===")
print(f"  breaker armed:  n={len([r for r in rows if r['armed']]):3d} cell-loss%={lr([r for r in rows if r['armed']]):4.1f}")
print(f"  breaker calm:   n={len([r for r in rows if not r['armed']]):3d} cell-loss%={lr([r for r in rows if not r['armed']]):4.1f}")
print(f"\n=== combined: tight-density ON TOP of breaker (does it add)? ===")
print(f"  calm + high-td: n={len([r for r in rows if not r['armed'] and r['td']>=q2]):3d} cell-loss%={lr([r for r in rows if not r['armed'] and r['td']>=q2]):4.1f}")
print(f"  calm + low-td:  n={len([r for r in rows if not r['armed'] and r['td']<q1]):3d} cell-loss%={lr([r for r in rows if not r['armed'] and r['td']<q1]):4.1f}")
print("\nREAD: theory holds if high tight-density -> higher cell-loss% (monotone), AND 'calm+high-td' lifts loss")
print("over 'calm+low-td' (tight-density catches what the breaker's calm state misses = leads it).")
