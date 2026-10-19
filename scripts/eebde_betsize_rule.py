"""Decode eebde's BET-SIZE rule: what market conditions make him bet HEAVY ($2000+) vs light?
Per btc/eth 5m window: his favorite total $, and market features at his early-commit ($300-crossing):
underlying lead toward favorite, 1h trend magnitude, ER (trend purity), favorite price. Which feature
best predicts his bet size? = 'what market judgment triggers his heavy bet'."""
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
    WT[r["slug"]].append((r.get("timestamp",0),r.get("outcome"),r.get("price",0) or 0,r.get("size",0) or 0,r.get("usdcSize",0) or 0))
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
BN={c:bn(SYM[c],min(sts)-3700,max(sts)+400) for c in SYM}
def feat(coin,st,favside,csec):
    d=BN[coin]; o=d.get(st)
    if not o: return None,None,None
    pm=d.get(st+(int(max(0,min(299,csec)))//60)*60)
    lead=(math.log(pm[1]/o[0])*1e4) if pm else 0
    leadf=lead if favside=="Up" else -lead
    p1=d.get(st-3600)
    net1h=(math.log(o[0]/p1[1])*1e4) if p1 else 0
    path=0;prev=p1[1] if p1 else o[0]
    for mm in range(60):
        q=d.get(st-3600+mm*60)
        if q: path+=abs(math.log(q[1]/prev)*1e4);prev=q[1]
    er=abs(net1h)/path if path>0 else 0
    return leadf,abs(net1h),er
rows=[]
for slug,trs in WT.items():
    coin="btc" if slug.startswith("btc") else "eth"; st=int(slug.split("-")[-1])
    trs.sort(key=lambda x:x[0]); cum=defaultdict(float); commit=None; cumsz=defaultdict(float); cumco=defaultdict(float)
    for ts,o,p,sz,usd in trs:
        cum[o]+=usd; cumsz[o]+=sz; cumco[o]+=usd
        if commit is None and cum[max(cum,key=cum.get)]>=300:
            commit=ts-st; break
    if commit is None: continue
    fav=max(cum,key=cum.get)
    full=defaultdict(float)
    for ts,o,p,sz,usd in trs: full[o]+=usd
    leadf,net1h,er=feat(coin,st,fav,commit)
    if leadf is None: continue
    favpx_commit=cumco[fav]/cumsz[fav] if cumsz[fav]>0 else 0
    rows.append({"betsize":full[fav],"leadf":leadf,"net1h":net1h,"er":er,"favpx":favpx_commit})
print("窗口:",len(rows),"\n")
def avgbet(rs): return statistics.median(r["betsize"] for r in rs) if rs else 0
def bigpct(rs): return sum(1 for r in rs if r["betsize"]>=2000)/len(rs)*100 if rs else 0
def show(name,key,bins):
    print("  [%s -> 下注额]"%name)
    for lo,hi in bins:
        s=[r for r in rows if lo<=r[key]<hi]
        if s: print("    %7.1f-%-7.1f: n=%-4d 中位下注$%-5.0f 重注(>=2000)占比%2.0f%%"%(lo,hi,len(s),avgbet(s),bigpct(s)))
show("入场时领先favorite bps","leadf",[(-99,0),(0,8),(8,20),(20,50),(50,999)])
show("1h趋势大小 bps","net1h",[(0,20),(20,50),(50,100),(100,999)])
show("趋势纯度 ER","er",[(0,0.05),(0.05,0.15),(0.15,0.3),(0.3,1.01)])
show("他建仓均价(把握)","favpx",[(0,0.5),(0.5,0.65),(0.65,0.8),(0.8,1.01)])
