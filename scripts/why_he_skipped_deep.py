"""Deep-dive: windows WE traded (DRY pass: max_lead>=15 & |lead|>=8) but eebde did NOT load heavy
(<1500) OR bet OPPOSITE. For each, pull his REAL per-trade sequence (data-api /trades) and reconstruct:
 - did he trade our side at all? total $ our side vs opposite
 - first/last trade offset (load duration); BIGGEST GAP (did he START then STOP loading?)
 - his avg entry px on favorite
 - lead path 0/60/120/180/240s -> did lead FADE/REVERSE/CHOP after his early phase?
 - our outcome
Goal: WHY he didn't load (faded/choppy/he-saw-reversal) = a filter we lack."""
import json,math,httpx,datetime
from collections import defaultdict
EEB="0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
# cross-ref
EF={}
for l in open("data/copy_cum_live.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if r.get("slug") and r.get("side"): EF[r["slug"]]={"fav":r["side"],"final":r.get("final_cum",0)}
OUR={}
for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if r.get("coin") in("btc","eth") and "won" in r and "-5m-" in r.get("slug","") and isinstance(r.get("B"),(int,float)):
        if (r.get("max_lead")or 0)>=15 and abs(r.get("lead",0)or 0)>=8: OUR[r["slug"]]=r
targets=[]
for s in OUR:
    if s in EF and (EF[s]["final"]<1500 or OUR[s]["side"]!=EF[s]["fav"]):
        kind="押反" if OUR[s]["side"]!=EF[s]["fav"] else "轻注"
        targets.append((s,kind))
print("深挖窗口(我们做他轻注/押反): %d\n"%len(targets))
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
def cid_of(slug):
    try:
        m=c.get("https://gamma-api.polymarket.com/markets",params={"slug":slug}).json()
        if isinstance(m,list) and m: return m[0].get("conditionId")
    except: pass
    return None
def kl(sym,st):
    try:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":(st-60)*1000,"endTime":(st+300)*1000,"limit":10}).json()
        return {int(x[0]//1000):float(x[4]) for x in k}
    except: return {}
rows=[]
for slug,kind in targets:
    coin="btc" if slug.startswith("btc") else "eth"; st=int(slug.split("-")[-1])
    cid=cid_of(slug)
    if not cid: continue
    try: trs=c.get("https://data-api.polymarket.com/trades",params={"market":cid,"limit":1000}).json()
    except: trs=[]
    et=[t for t in trs if (t.get("proxyWallet","") or "").lower()==EEB and (t.get("side","")or"").upper()=="BUY"]
    side=OUR[slug]["side"]
    usd_side=sum((t.get("usdcSize")or 0) for t in et if t.get("outcome")==side)
    usd_opp=sum((t.get("usdcSize")or 0) for t in et if t.get("outcome")!=side)
    offs=sorted((t.get("timestamp",0)-st) for t in et)
    fav_tr=[t for t in et if t.get("outcome")==(EF[slug]["fav"])]
    favpx=(sum((t.get("price")or 0)*(t.get("usdcSize")or 0) for t in fav_tr)/sum((t.get("usdcSize")or 0) for t in fav_tr)) if fav_tr else 0
    first=offs[0] if offs else None; last=offs[-1] if offs else None
    maxgap=max((offs[i+1]-offs[i] for i in range(len(offs)-1)),default=0)
    d=kl(SYM[coin],st); op=d.get(st) or d.get(st-60)
    def L(sec):
        p=d.get(st+sec); return (math.log(p/op)*1e4 if side=="Up" else -math.log(p/op)*1e4) if (p and op) else None
    lp=[L(s) for s in (0,60,120,180,240)]
    rows.append({"slug":slug,"kind":kind,"won":OUR[slug]["won"],"nt":len(et),"us":usd_side,"uo":usd_opp,
        "first":first,"last":last,"gap":maxgap,"favpx":favpx,"final":EF[slug]["final"],"lp":lp,
        "hr":datetime.datetime.utcfromtimestamp(st).strftime("%H:%M")})
# 汇总
def fmtlp(lp): return "/".join((("%+.0f"%x) if x is not None else "·") for x in lp)
print("时间   类型 我赢 他笔数 他$本侧 他$反侧 首/末s 最大停顿s favpx finalcum | lead路径0/1/2/3/4m")
for r in sorted(rows,key=lambda x:x["hr"]):
    print("%s %s %s n=%-3d %6.0f %6.0f %4s/%-4s gap=%-3.0f %.2f %5.0f | %s"%(
        r["hr"],r["kind"],("赢" if r["won"] else "亏"),r["nt"],r["us"],r["uo"],
        str(r["first"]),str(r["last"]),r["gap"],r["favpx"],r["final"],fmtlp(r["lp"])))
# 分类他为啥没加载
print("\n=== 他不加载的原因分类 ===")
cat=defaultdict(lambda:[0,0])
for r in rows:
    lp=r["lp"]; rev = lp[0] is not None and lp[-1] is not None and lp[-1]<lp[0]-3
    if r["kind"]=="押反": k="他押反方向(他看到反转)"
    elif r["last"] is not None and r["last"]<90: k="他早早收手(<90s就停)"
    elif r["gap"]>=60: k="他中途长时间停顿(>=60s不加)"
    elif rev: k="lead后段衰减/反转他不追"
    elif r["nt"]<=3: k="他几乎没下(<=3笔)"
    else: k="他下了只是没到1500(资金/节奏)"
    cat[k][0]+=1; cat[k][1]+=(1 if r["won"] else 0)
for k,(n,w) in sorted(cat.items(),key=lambda x:-x[1][0]):
    print("  %-26s n=%-3d 我们胜%2.0f%%"%(k,n,w/n*100 if n else 0))
