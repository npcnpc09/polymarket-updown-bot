"""real_vs_market_reversal.py — per-day: (A) binance MARKET reversal rate on OUR setups (reconstruction: early-
lead@min3 vs settle, z>=2.5 & |lead|>=8) vs (B) OUR REAL loss rate (cell+taker). If the MARKET reversal rate is
flat but our REAL loss rate spikes recently -> the 'phenomenon' is NOT in btc price (it's outcome clustering /
relational), which is why no price indicator finds it. If BOTH spike together -> there IS a market reversal
phenomenon to chase."""
import httpx, math, statistics as st, json, time
from datetime import datetime, timezone
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}
now=int(time.time()); start=now-11*86400
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
# (A) market reversal on our setups, per day
mkt={}
for coin,sym in COINS.items():
    k=klines_1m(sym,start,now); O={t:o for t,o,c in k}; C={t:c for t,o,c in k}
    t=start-(start%300)
    while t+300<=now:
        op=O.get(t); m3=C.get(t+180); cl=C.get(t+300) or O.get(t+300)
        cl1=[C.get(t-60*i) for i in range(1,31)]; cl1=[x for x in cl1 if x]
        if op and m3 and cl and len(cl1)>=20:
            v30=st.pstdev([math.log(cl1[i]/cl1[i-1])*1e4 for i in range(1,len(cl1))])
            lead3=math.log(m3/op)*1e4
            if v30>0 and abs(lead3)>=8 and abs(lead3)/v30>=2.5:
                d=datetime.fromtimestamp(t,timezone.utc).strftime("%m-%d")
                rec=mkt.setdefault(d,[0,0]); rec[0]+=1
                if (lead3>=0)!=(cl>=op): rec[1]+=1
        t+=300
# (B) our real loss rate per day (cell+taker)
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
real={}
for f,keep in (("data/multi_window_engine_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None),
               ("data/early_taker_probe.jsonl",lambda o:o.get("kind")=="entry" and o.get("won") is not None)):
    for o in (json.loads(l) for l in open(ROOT+"/"+f,encoding="utf-8") if l.strip()):
        if keep(o):
            w=ws_of(o.get("slug",""))
            if w and w>=start:
                d=datetime.fromtimestamp(w,timezone.utc).strftime("%m-%d")
                rec=real.setdefault(d,[0,0]); rec[0]+=1
                if not o["won"]: rec[1]+=1
print(f"{'day':6s} | {'MARKET rev% (recon, our setups)':32s} | {'OUR REAL loss% (cell+taker)':28s}")
for d in sorted(set(mkt)|set(real)):
    m=mkt.get(d,[0,0]); r=real.get(d,[0,0])
    mr=f"{m[1]/m[0]*100:4.1f}%  (n={m[0]})" if m[0] else "  -"
    rr=f"{r[1]/r[0]*100:4.1f}%  (n={r[0]})" if r[0] else "  -"
    print(f"{d:6s} | {mr:32s} | {rr:28s}")
print("\nREAD: if MARKET rev% is flat ~1-4% across all days while OUR REAL loss% swings 3%->17% -> the phenomenon")
print("is NOT a market-price reversal change; it's outcome clustering (overdispersion) w/ no price correlate.")
