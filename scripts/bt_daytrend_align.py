"""bt_daytrend_align.py — test the user's idea: does aligning our 5m/15m fill DIRECTION with the
already-realized DAY-LEVEL binance trend (past 4h / 12h net move) improve real PnL?
NOT prediction — uses only data BEFORE each fill (the realized multi-hour trend at entry time).
For each real fill: side(Up/Down) vs sign(past-Nh net move) => aligned / counter. Compare win%/net/EV.
Held-out 60/40. Caveat in memory: a prior 'trend-align' (via ER) FAILED OOS — re-testing with day net-move axis."""
import json, statistics as st, urllib.request
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
# load real fills
R=[]
for l in open(ROOT+"/data/multi_window_engine_live.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    try:o=json.loads(l)
    except:continue
    if o.get("filled") and o.get("won") is not None and o.get("pnl") is not None:
        ws=ws_of(o.get("slug",""))
        if ws is None: continue
        R.append({"ws":ws,"eng":"cell","coin":o.get("coin"),"side":o.get("side"),
                  "won":bool(o["won"]),"pnl":float(o["pnl"]),"sh":float(o.get("sh",5) or 5)})
for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    try:o=json.loads(l)
    except:continue
    if o.get("kind")=="entry" and o.get("won") is not None:
        ws=ws_of(o.get("slug",""))
        if ws is None: continue
        R.append({"ws":ws,"eng":"taker","coin":o.get("coin"),"side":o.get("side"),
                  "won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),"sh":5.0})
R=[r for r in R if r["coin"] in ("btc","eth") and r["side"] in ("Up","Down")]
R.sort(key=lambda x:x["ws"])
if not R: print("no fills"); raise SystemExit
print("btc/eth fills:",len(R),"ws range",R[0]["ws"],"->",R[-1]["ws"])
# pull 1h klines covering the range (limit 1000 ~ 41 days)
def klines(sym):
    u="https://api.binance.com/api/v3/klines?symbol={}&interval=1h&limit=1000".format(sym)
    d=json.load(urllib.request.urlopen(u,timeout=15))
    return [(int(k[0]//1000), float(k[4])) for k in d]  # (openTime_sec, close)
K={"btc":klines("BTCUSDT"),"eth":klines("ETHUSDT")}
def trend_bps(coin, ws, hrs):
    arr=K[coin]
    # index of last bar with openTime <= ws
    lo,hi=0,len(arr)-1; idx=-1
    while lo<=hi:
        m=(lo+hi)//2
        if arr[m][0]<=ws: idx=m; lo=m+1
        else: hi=m-1
    if idx<hrs: return None
    c_now=arr[idx][1]; c_then=arr[idx-hrs][1]
    return (c_now/c_then-1)*1e4
def sgn(x): return 1 if x>0 else (-1 if x<0 else 0)
for r in R:
    r["t4"]=trend_bps(r["coin"],r["ws"],4)
    r["t12"]=trend_bps(r["coin"],r["ws"],12)
    r["sdir"]=1 if r["side"]=="Up" else -1
def stat(s):
    if not s: return "n=0"
    w=sum(1 for t in s if t["won"]); net=sum(t["pnl"] for t in s); ev=st.mean([t["pnl"]/t["sh"] for t in s])
    return "n={:4d} win%={:5.1f} net=${:+8.2f} EV/sh={:+.3f}".format(len(s),w/len(s)*100,net,ev)
for H,key in ((4,"t4"),(12,"t12")):
    rr=[r for r in R if r[key] is not None and abs(r[key])>=10]  # require a real trend (>=10bps over Nh)
    print("\n=== past-{}h trend (|move|>=10bps), n={} ===".format(H,len(rr)))
    al=[r for r in rr if r["sdir"]==sgn(r[key])]; ct=[r for r in rr if r["sdir"]==-sgn(r[key])]
    print("  ALIGNED (side==trend) : "+stat(al))
    print("  COUNTER (side!=trend) : "+stat(ct))
    # held-out
    n=len(rr); cut=int(n*0.6); tr=rr[:cut]; hd=rr[cut:]
    def pol(d,keep): s=[t for t in d if keep(t)]; return (len(s),sum(t["pnl"] for t in s),(st.mean([t['pnl']/t['sh'] for t in s]) if s else 0))
    for lab,keep in (("aligned",lambda r:r["sdir"]==sgn(r[key])),("counter",lambda r:r["sdir"]==-sgn(r[key]))):
        fn,ff,fe=pol(rr,keep); _,tf,te=pol(tr,keep); hn,hf,he=pol(hd,keep)
        print("    {:8s} FULL {:4d}/${:+7.2f}/{:+.3f} | TRAIN ${:+7.2f} | HELD {:4d}/${:+7.2f}/{:+.3f}".format(lab,fn,ff,fe,tf,hn,hf,he))
print("\nREAD: if ALIGNED >> COUNTER on net/EV AND holds held-out, day-trend side-bias is a real signal.")
print("If counter is not clearly worse (or it flips OOS), it confirms the prior result: direction/trend-align is NOT a leak.")
