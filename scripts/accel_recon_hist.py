"""Reconstruct accel from binance for ALL historical DRY 5m btc/eth settled trades (2.5 days, no accel
label needed), bucket by accel to validate the accel>=10 finding on a big sample.
accel = (lead_entry - lead_early) toward side; lead_early@60s, lead_entry@~150s (interp 120/180).
Uses recorded won/B/side (actual outcomes); cushion/max_lead also reconstructed for the self-taker filter."""
import json,math,httpx,statistics
ROWS=[]
for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if "won" in r and isinstance(r.get("B"),(int,float)) and r.get("coin")in("btc","eth") and "-5m-" in r.get("slug",""):
        ROWS.append(r)
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
sts=[int(r["slug"].split("-")[-1]) for r in ROWS]
lo,hi=min(sts)-120,max(sts)+360
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
def fetch(sym):
    out={}; cur=lo
    while cur<hi:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=float(x[1])  # open price at minute
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
BN={cn:fetch(SYM[cn]) for cn in SYM}
print("binance分钟数: btc=%d eth=%d"%(len(BN["btc"]),len(BN["eth"])))
def px(cn,t): return BN[cn].get(t)
recs=[]
for r in ROWS:
    cn=r["coin"]; st=int(r["slug"].split("-")[-1])
    o=px(cn,st)
    if not o: continue
    def L(off):
        p=px(cn,st+off); return math.log(p/o)*1e4 if p else None
    le=L(60); l120=L(120); l180=L(180); l240=L(240)
    if le is None or l120 is None or l180 is None: continue
    lead_entry=(l120+l180)/2.0           # ~150s entry proxy
    side="Up" if lead_entry>=0 else "Down"
    accel=(lead_entry-le)*(1 if lead_entry>=0 else -1)
    cushion=abs(lead_entry)
    maxl=max(abs(x) for x in (le,l120,l180,l240) if x is not None)
    recs.append({"won":r["won"],"B":r["B"],"accel":accel,"cushion":cushion,"maxl":maxl,
                 "rec_side":r.get("side"),"side":side})
print("重建成功: %d/%d\n"%(len(recs),len(ROWS)))
BK=[(-1e9,0,"<=0"),(0,5,"0-5"),(5,10,"5-10"),(10,15,"10-15"),(15,20,"15-20"),(20,1e9,"20+")]
def report(rs,title):
    print("========== %s (n=%d) =========="%(title,len(rs)))
    for lo_,hi_,lbl in BK:
        b=[r for r in rs if (r["accel"]<=hi_ if lo_==-1e9 else lo_<r["accel"]<=hi_)]
        cum=[r for r in rs if r["accel"]>lo_]
        if not b: print("  %-7s 0"%lbl); continue
        w=sum(1 for r in b if r["won"]); ev=sum((5*(1-r["B"]) if r["won"] else -5*r["B"]) for r in b)/len(b)
        cw=sum(1 for r in cum if r["won"])/len(cum)*100 if cum else 0
        cev=sum((5*(1-r["B"]) if r["won"] else -5*r["B"]) for r in cum)/len(cum) if cum else 0
        print("  %-7s n=%4d 胜%3.0f%% EV%+.2f | >%-3.0f累计: 胜%2.0f%% EV%+.2f n=%d"%(lbl,len(b),w/len(b)*100,ev,lo_ if lo_!=-1e9 else 0,cw,cev,len(cum)))
report(recs,"全部 5m btc/eth (2.5天)")
print()
filt=[r for r in recs if r["cushion"]>=8 and r["maxl"]>=15]
report(filt,"+cushion(|lead|>=8 & maxL>=15) 自营条件")
