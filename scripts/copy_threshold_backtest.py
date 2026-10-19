"""Backtest the copy-EARLIER question: for each btc/eth 5m window in eebde's 7d history, track his
running cumulative $ per side; when the FAVORITE side first crosses $300/$500/$1000, record his price
at that crossing (~what we'd pay following as a taker) + the side. Winner via binance net (=Chainlink
at >=5bps). Compare per-threshold: price paid, win%, EV=win-price. Earlier=cheaper but less confirmed?"""
import json,re,httpx,math,datetime
from collections import defaultdict
EF="data/eebde_history_7d.jsonl"
WT=defaultdict(list)  # slug -> list of (ts, outcome, price, size)
for ln in open(EF,encoding="utf-8"):
    ln=ln.strip()
    if not ln: continue
    try: r=json.loads(ln)
    except: continue
    if r.get("type")!="TRADE" or (r.get("side") or "").upper()!="BUY": continue
    m=re.match(r"(btc|eth)-updown-5m-(\d+)",r.get("slug","") or "")
    if not m or r.get("outcome") not in ("Up","Down"): continue
    WT[r["slug"]].append((r.get("timestamp",0),r.get("outcome"),r.get("price",0) or 0,r.get("size",0) or 0))
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
sts=[int(s.split("-")[-1]) for s in WT]
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
def winner(slug):
    c="btc" if slug.startswith("btc") else "eth"; st=int(slug.split("-")[-1]); d=BN[c]
    o=d.get(st) or d.get(st+1); cl=d.get(st+240) or d.get(st+300)
    return ("Up" if cl[1]>=o[0] else "Down") if (o and cl) else None
THR=[300,500,1000,2000]
rows={t:[] for t in THR}
for slug,trs in WT.items():
    w=winner(slug)
    if not w: continue
    trs.sort(key=lambda x:x[0])
    cum=defaultdict(float); crossed={t:False for t in THR}
    for ts,o,p,sz in trs:
        cum[o]+=p*sz
        fav=max(cum,key=cum.get)
        for t in THR:
            if not crossed[t] and cum[fav]>=t:
                crossed[t]=True
                rows[t].append({"side":fav,"price":p,"win":fav==w,"sec":ts-int(slug.split("-")[-1])})
print("eebde btc/eth 窗口:",len(WT),"\n")
print("%-8s %5s %7s %7s %8s %8s"%("门槛$","n","均价","胜率","EV(胜-价)","入场秒"))
import statistics
for t in THR:
    rs=rows[t]
    if not rs: continue
    px=statistics.mean(r["price"] for r in rs)
    wr=sum(1 for r in rs if r["win"])/len(rs)*100
    ev=wr/100-px
    sec=statistics.median(r["sec"] for r in rs)
    print("$%-7d %5d %7.3f %6.0f%% %+8.3f %7.0fs"%(t,len(rs),px,wr,ev,sec))
print("\n注: EV=胜率-均价(每股, 未含taker点差~+1-2分). 越大越好. 早门槛便宜但确认少.")
