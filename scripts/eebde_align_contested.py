"""Same OOS backtest but restricted to CONTESTED windows (where the artifact 'min3-lead trivially wins'
breaks down). Contested measured 2 ways: (a) eebde's favorite avg price moderate (he wasn't sure either),
(b) small final net move (close call). In contested windows, does OUR-aligned-with-eebde beat OUR-against?"""
import json,re,httpx,math,datetime
from collections import defaultdict
EF="data/eebde_history_7d.jsonl"
EVAL=defaultdict(lambda:defaultdict(float)); ESZ=defaultdict(lambda:defaultdict(float))
for ln in open(EF,encoding="utf-8"):
    ln=ln.strip()
    if not ln: continue
    try: r=json.loads(ln)
    except: continue
    if r.get("type")!="TRADE" or (r.get("side") or "").upper()!="BUY": continue
    m=re.match(r"(btc|eth)-updown-5m-(\d+)",r.get("slug","") or "")
    if not m or r.get("outcome") not in ("Up","Down"): continue
    p=r.get("price",0) or 0; sz=r.get("size",0) or 0
    EVAL[r["slug"]][r["outcome"]]+=p*sz; ESZ[r["slug"]][r["outcome"]]+=sz
def efav(s):
    d=EVAL.get(s); return max(d,key=d.get) if d else None
def efav_px(s):
    f=efav(s)
    if not f: return None
    return EVAL[s][f]/ESZ[s][f] if ESZ[s][f]>0 else None
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
slugs=list(EVAL); sts=[int(s.split("-")[-1]) for s in slugs]
def bn(sym,t0,t1):
    out={};cur=t0
    while cur<t1:
        k=httpx.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":t1*1000,"limit":1000},timeout=20).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=float(x[4])
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
BN={c:bn(SYM[c],min(sts)-120,max(sts)+400) for c in SYM}
def px(c,t):
    d=BN[c]
    for dd in range(3):
        if t+dd in d: return d[t+dd]
    return None
rows=[]
for s in slugs:
    c="btc" if s.startswith("btc") else "eth"; st=int(s.split("-")[-1])
    op=px(c,st); pe=px(c,st+180); cl=px(c,st+240) or px(c,st+300)
    if not(op and pe and cl): continue
    peak=0
    for mm in range(4):
        q=px(c,st+mm*60)
        if q: peak=max(peak,abs(math.log(q/op)*1e4))
    lead=math.log(pe/op)*1e4
    if peak<15 or abs(lead)<8: continue
    side="Up" if lead>=0 else "Down"
    net=math.log(cl/op)*1e4
    won=(side=="Up")==(cl>=op)
    fav=efav(s); fpx=efav_px(s)
    rows.append({"side":side,"won":won,"aligned":(fav==side) if fav else None,"favpx":fpx,"net":abs(net)})
def wr(rs): return sum(1 for r in rs if r["won"])/len(rs)*100 if rs else 0
def rep(rs,lab):
    al=[r for r in rs if r["aligned"]==True]; ag=[r for r in rs if r["aligned"]==False]
    print("  %-34s 同向 n=%-3d %3.0f%% | 押反 n=%-3d %3.0f%%"%(lab,len(al),wr(al),len(ag),wr(ag)))
print("总 OUR-signal 窗口:",len(rows),"\n")
print("按争议度(eebde favorite 均价 = 他的把握):")
rep([r for r in rows if r["favpx"] and r["favpx"]<0.6],"争议大 favpx<0.60")
rep([r for r in rows if r["favpx"] and 0.6<=r["favpx"]<0.75],"中等 favpx 0.60-0.75")
rep([r for r in rows if r["favpx"] and r["favpx"]>=0.75],"清晰 favpx>=0.75")
print("\n按结果接近度(|净移动|越小越是close call):")
rep([r for r in rows if r["net"]<10],"close call |net|<10bps")
rep([r for r in rows if r["net"]<20],"|net|<20bps")
rep([r for r in rows if r["net"]>=30],"决定性 |net|>=30bps")
