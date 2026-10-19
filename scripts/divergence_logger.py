"""Continuous he-vs-us divergence logger. cid-based history is impossible (cid only resolvable for
recent windows) so we FORWARD-log: every ~90s pull eebde's recent activity (live, complete for current
windows), bucket by slug; for each window OUR DRY self-taker entered (max_lead>=15 & |lead|>=8) that has
SETTLED and is still in his covered range, snapshot his full sequence + classify WHY he didn't load our
side, with our outcome. Dedup by slug. Accumulates data/divergence.jsonl over days -> real sample."""
import json,math,httpx,time,os
from collections import defaultdict
EEB="0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
OUT="data/divergence.jsonl"
def now(): return int(time.time())
def load_seen():
    s=set()
    if os.path.exists(OUT):
        for l in open(OUT,encoding="utf-8"):
            try: s.add(json.loads(l)["slug"])
            except: pass
    return s
def his_activity(c):
    A=[]
    for off in range(0,2000,500):
        try: a=c.get("https://data-api.polymarket.com/activity",params={"user":EEB,"limit":500,"offset":off}).json()
        except: break
        if not isinstance(a,list) or not a: break
        A+=[x for x in a if x.get("type")=="TRADE" and (x.get("side","")or"").upper()=="BUY"]
        if len(a)<500: break
    return A
def our_entries():
    R={}
    try:
        for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
            l=l.strip()
            if not l: continue
            try: r=json.loads(l)
            except: continue
            if r.get("coin")in("btc","eth") and "won" in r and "-5m-" in r.get("slug","") and isinstance(r.get("B"),(int,float)):
                if (r.get("max_lead")or 0)>=15 and abs(r.get("lead",0)or 0)>=8: R[r["slug"]]=r
    except FileNotFoundError: pass
    return R
def kl(c,sym,st):
    try:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":(st-60)*1000,"endTime":(st+300)*1000,"limit":10}).json()
        return {int(x[0]//1000):float(x[1]) for x in k}
    except: return {}
def classify(r):
    lp=r["lp"]; rev=lp[0] is not None and lp[3] is not None and lp[3]<lp[0]-3
    if r["nt"]==0: return "absent"
    if r["uo"]>r["us"]*1.2: return "opposite"
    if r["last"] is not None and r["last"]<90: return "early_stop"
    if r["gap"]>=70: return "mid_gap"
    if rev: return "lead_faded"
    if r["us"]<300: return "light_ourside"
    return "loaded_sub1500"
def run():
    c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
    while True:
        try:
            seen=load_seen(); ACT=his_activity(c)
            if ACT:
                tmin=min(x["timestamp"] for x in ACT); tmax=max(x["timestamp"] for x in ACT)
                HB=defaultdict(list)
                for x in ACT:
                    s=x.get("slug","")
                    if "-updown-5m-" in s: HB[s].append(x)
                OUR=our_entries()
                wrote=0
                for slug,r in OUR.items():
                    if slug in seen: continue
                    st=int(slug.split("-")[-1])
                    if st<tmin or st+300>now()-30: continue   # settled + in covered range
                    coin=r["coin"]; side=r["side"]; et=HB.get(slug,[])
                    us=sum((t.get("usdcSize")or 0) for t in et if t.get("outcome")==side)
                    uo=sum((t.get("usdcSize")or 0) for t in et if t.get("outcome")!=side)
                    offs=sorted(t["timestamp"]-st for t in et)
                    first=offs[0] if offs else None; last=offs[-1] if offs else None
                    gap=max((offs[i+1]-offs[i] for i in range(len(offs)-1)),default=0)
                    d=kl(c,SYM[coin],st); op=d.get(st) or d.get(st-60)
                    def L(sec):
                        p=d.get(st+sec); return round((math.log(p/op)*1e4 if side=="Up" else -math.log(p/op)*1e4),1) if(p and op) else None
                    rec={"slug":slug,"coin":coin,"side":side,"won":r["won"],"B":r.get("B"),
                        "max_lead":r.get("max_lead"),"lead":r.get("lead"),"accel":r.get("accel"),
                        "nt":len(et),"us":round(us),"uo":round(uo),"first":first,"last":last,"gap":gap,
                        "lp":[L(s) for s in (0,60,120,180,240)],"ts":now()}
                    rec["cat"]=classify(rec)
                    with open(OUT,"a",encoding="utf-8") as f: f.write(json.dumps(rec)+"\n")
                    wrote+=1
                if wrote: print("logged",wrote,flush=True)
        except Exception as e:
            print("err",repr(e)[:120],flush=True)
        time.sleep(90)
if __name__=="__main__": run()
