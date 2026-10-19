"""Deep-dive (activity-based, no cid needed): pull eebde's recent activity, bucket by slug into full
per-window sequences. For OUR DRY entries (self-taker pass) inside his covered time-range, reconstruct
HIS behavior + classify WHY he didn't load heavy:
  ABSENT (0 trades) / OPPOSITE side / EARLY-STOP (last trade <90s) / GAP (stopped loading) /
  FADE (lead reversed after his early phase) / LIGHT (loaded our side but <1500).
Plus his sequence detail + lead path + our outcome. = why he skips what we take."""
import json,math,httpx,datetime
from collections import defaultdict
EEB="0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
# pull his recent activity (paginate to offset cap)
ACT=[]
for off in range(0,3000,500):
    try: a=c.get("https://data-api.polymarket.com/activity",params={"user":EEB,"limit":500,"offset":off}).json()
    except: break
    if not isinstance(a,list) or not a: break
    ACT+=[x for x in a if x.get("type")=="TRADE" and (x.get("side","")or"").upper()=="BUY"]
    if len(a)<500: break
if not ACT: print("无活动"); raise SystemExit
tmin=min(x["timestamp"] for x in ACT); tmax=max(x["timestamp"] for x in ACT)
print("他活动覆盖: %s ~ %s  (%d笔)\n"%(datetime.datetime.utcfromtimestamp(tmin).strftime("%H:%M"),datetime.datetime.utcfromtimestamp(tmax).strftime("%H:%M"),len(ACT)))
# bucket by slug
HB=defaultdict(list)
for x in ACT:
    s=x.get("slug","")
    if "-updown-5m-" in s and (s.startswith("btc")or s.startswith("eth")): HB[s].append(x)
# our DRY entries (self-taker pass) inside covered range
OUR=[]
for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if r.get("coin") in("btc","eth") and "won" in r and "-5m-" in r.get("slug","") and isinstance(r.get("B"),(int,float)):
        st=int(r["slug"].split("-")[-1])
        if st>=tmin and st<=tmax and (r.get("max_lead")or 0)>=15 and abs(r.get("lead",0)or 0)>=8:
            OUR.append(r)
print("覆盖时段内我们自营会下的窗口: %d\n"%len(OUR))
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
def kl(sym,st):
    try:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":(st-60)*1000,"endTime":(st+300)*1000,"limit":10}).json()
        return {int(x[0]//1000):float(x[1]) for x in k}
    except: return {}
rows=[]
for r in OUR:
    slug=r["slug"]; coin=r["coin"]; st=int(slug.split("-")[-1]); side=r["side"]
    et=HB.get(slug,[])
    us=sum((t.get("usdcSize")or 0) for t in et if t.get("outcome")==side)
    uo=sum((t.get("usdcSize")or 0) for t in et if t.get("outcome")!=side)
    favside="Up" if us>=uo else "Down"  # his money-favorite
    offs=sorted(t["timestamp"]-st for t in et)
    first=offs[0] if offs else None; last=offs[-1] if offs else None
    gap=max((offs[i+1]-offs[i] for i in range(len(offs)-1)),default=0)
    d=kl(SYM[coin],st); op=d.get(st) or d.get(st-60)
    def L(sec):
        p=d.get(st+sec); return (math.log(p/op)*1e4 if side=="Up" else -math.log(p/op)*1e4) if(p and op) else None
    lp=[L(s) for s in (0,60,120,180,240)]
    rows.append({"slug":slug,"hr":datetime.datetime.utcfromtimestamp(st).strftime("%H:%M"),"won":r["won"],
        "side":side,"nt":len(et),"us":us,"uo":uo,"favside":favside,"first":first,"last":last,"gap":gap,"lp":lp})
def fmtlp(lp): return "/".join((("%+.0f"%x) if x is not None else "·") for x in lp)
print("时间  我侧 赢亏 他笔 他$本侧 他$反 首/末s 停顿 | lead 0/1/2/3/4m")
for r in sorted(rows,key=lambda x:x["hr"]):
    print("%s %-4s %s n=%-3d %6.0f %5.0f %4s/%-4s g=%-3.0f| %s"%(r["hr"],r["side"],("赢"if r["won"]else"亏"),
        r["nt"],r["us"],r["uo"],str(r["first"]),str(r["last"]),r["gap"],fmtlp(r["lp"])))
print("\n=== 他为什么不加载本侧 (分类) ===")
cat=defaultdict(lambda:[0,0])
for r in rows:
    lp=r["lp"]; rev=lp[0] is not None and lp[3] is not None and lp[3]<lp[0]-3
    tot=r["us"]+r["uo"]
    if r["nt"]==0: k="完全缺席(0笔)"
    elif r["uo"]>r["us"]*1.2: k="他押反方向(钱在反侧)"
    elif r["last"] is not None and r["last"]<90: k="早早收手(<90s停)"
    elif r["gap"]>=70: k="中途长停顿(>=70s不加)"
    elif rev: k="lead后段反转他不追"
    elif r["us"]<300: k="本侧很轻(<300$)"
    else: k="下了本侧只是没到1500"
    cat[k][0]+=1; cat[k][1]+=(1 if r["won"] else 0)
for k,(n,w) in sorted(cat.items(),key=lambda x:-x[1][0]):
    print("  %-22s n=%-3d 我们胜%2.0f%%"%(k,n,w/n*100 if n else 0))
