"""At eebde's $1000-favorite-crossing moment, which REAL-TIME features (available then, no hindsight)
predict the favorite WINS / he keeps loading to $1500? If one separates win/loss, it's a usable filter
at $1000 (cheap entry) to skip the weak-confirmation losers. Features at $1000: time-to-reach,
his avg price, loading speed, recent acceleration, value dominance, underlying lead."""
import json,re,httpx,math,statistics
from collections import defaultdict
EF="data/eebde_history_7d.jsonl"
WT=defaultdict(list)
for ln in open(EF,encoding="utf-8"):
    ln=ln.strip()
    if not ln: continue
    try: r=json.loads(ln)
    except: continue
    if r.get("type")!="TRADE" or (r.get("side") or "").upper()!="BUY": continue
    m=re.match(r"(btc|eth)-updown-5m-(\d+)",r.get("slug","") or "")
    if not m or r.get("outcome") not in ("Up","Down"): continue
    WT[r["slug"]].append((r.get("timestamp",0),r.get("outcome"),r.get("price",0) or 0,r.get("size",0) or 0))
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}; sts=[int(s.split("-")[-1]) for s in WT]
def bn(sym,t0,t1):
    out={};cur=t0
    while cur<t1:
        k=httpx.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":t1*1000,"limit":1000},timeout=20).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[4]))
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
BN={c:bn(SYM[c],min(sts)-120,max(sts)+400) for c in SYM}
def win_lead(slug,sec,favside):
    c="btc" if slug.startswith("btc") else "eth"; st=int(slug.split("-")[-1]); d=BN[c]
    o=d.get(st) or d.get(st+1); cl=d.get(st+240) or d.get(st+300)
    if not o or not cl: return None,None
    w="Up" if cl[1]>=o[0] else "Down"
    pm=d.get(st+(int(sec)//60)*60)
    lead=(math.log(pm[1]/o[0])*1e4) if pm else 0
    return w,(lead if favside=="Up" else -lead)
rows=[]
for slug,trs in WT.items():
    st=int(slug.split("-")[-1]); trs.sort(key=lambda x:x[0])
    cum=defaultdict(float); cumsz=defaultdict(float); cumpxsz=defaultdict(float)
    crossed=None; recent=[]
    for ts,o,p,sz in trs:
        cum[o]+=p*sz; cumsz[o]+=sz; cumpxsz[o]+=p*sz; recent.append((ts,p*sz))
        fav=max(cum,key=cum.get)
        if crossed is None and cum[fav]>=1000:
            t=ts-st
            avgpx=cumpxsz[fav]/cumsz[fav] if cumsz[fav]>0 else 0
            other=cum.get("Up" if fav=="Down" else "Down",0)
            dom=cum[fav]/(cum[fav]+other) if (cum[fav]+other)>0 else 0
            rate15=sum(v for tt,v in recent if tt>=ts-15)   # $ loaded in last 15s
            crossed={"t":t,"fav":fav,"avgpx":avgpx,"dom":dom,"rate15":rate15,"speed":1000/t if t>0 else 0}
            break
    if not crossed: continue
    w,leadf=win_lead(slug,max(0,min(299,crossed["t"])),crossed["fav"])
    if w is None: continue
    final=cum[crossed["fav"]]   # his final cum on favorite
    # but cum here only built to crossing; need full final — recompute
    fullcum=defaultdict(float)
    for ts,o,p,sz in trs: fullcum[o]+=p*sz
    crossed.update({"win":crossed["fav"]==w,"reach1500":fullcum[crossed["fav"]]>=1500,"leadf":leadf})
    rows.append(crossed)
print("窗口:",len(rows),"\n")
def wr(rs): return sum(1 for r in rs if r["win"])/len(rs)*100 if rs else 0
def r15(rs): return sum(1 for r in rs if r["reach1500"])/len(rs)*100 if rs else 0
print("=== 各 $1000-时刻特征 vs 胜率/到$1500率 ===")
def feat(name,key,bins):
    print("  [%s]"%name)
    for lo,hi in bins:
        s=[r for r in rows if lo<=r[key]<hi]
        if s: print("    %6.2f-%-6.2f: n=%-4d 胜%2.0f%% 到$1500=%2.0f%%"%(lo,hi,len(s),wr(s),r15(s)))
feat("他均价 avgpx","avgpx",[(0,0.5),(0.5,0.65),(0.65,0.8),(0.8,1.01)])
feat("到$1000耗时(秒)","t",[(0,60),(60,120),(120,200),(200,400)])
feat("加仓集中度 dom(fav占比)","dom",[(0.5,0.7),(0.7,0.85),(0.85,1.01)])
feat("近15秒加仓$ rate15","rate15",[(0,200),(200,600),(600,1e9)])
feat("标的领先favorite方向 bps","leadf",[(-99,0),(0,10),(10,30),(30,999)])
