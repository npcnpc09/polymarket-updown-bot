"""Backtest copying eebde's BIG SINGLE trades (>= $2000). For each btc/eth window, find his biggest
single trade; if >= threshold, simulate copying THAT side as a taker at his_price + spread, resolve
(binance). Report win% / price (priced-in?) / EV per share + $ at 5/10/20 shares. Also by day (OOS)."""
import json,re,httpx,math,datetime,statistics
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
    WT[r["slug"]].append((r.get("timestamp",0),r.get("outcome"),r.get("price",0) or 0,r.get("usdcSize",0) or 0))
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
def winner(slug):
    c="btc" if slug.startswith("btc") else "eth"; st=int(slug.split("-")[-1]); d=BN[c]
    o=d.get(st) or d.get(st+1); cl=d.get(st+240) or d.get(st+300)
    return ("Up" if cl[1]>=o[0] else "Down") if (o and cl) else None
SPREAD=0.015
def run(thr):
    rows=[]
    for slug,trs in WT.items():
        w=winner(slug)
        if not w: continue
        big=max(trs,key=lambda x:x[3])   # biggest single by usdcSize
        if big[3]<thr: continue
        ts,side,p,usd=big
        ask=min(p+SPREAD,0.98)
        rows.append({"day":datetime.datetime.utcfromtimestamp(int(slug.split("-")[-1])).strftime("%m-%d"),
                     "win":side==w,"ask":ask,"ev":(1-ask) if side==w else -ask,"sec":ts-int(slug.split("-")[-1])})
    return rows
for thr in (1000,2000,3000):
    rs=run(thr)
    if not rs: continue
    wr=sum(1 for r in rs if r["win"])/len(rs)*100
    apx=statistics.mean(r["ask"] for r in rs); ev=statistics.mean(r["ev"] for r in rs)
    sec=statistics.median(r["sec"] for r in rs)
    print("单笔>=$%-5d: n=%-3d 胜%2.0f%% 均价%.3f EV/股%+.3f | 5股%+.2f 10股%+.2f 20股%+.2f | 中位入场%ds"%(
        thr,len(rs),wr,apx,ev,ev*5,ev*10,ev*20,sec))
    # 按天 OOS
    days=sorted(set(r["day"] for r in rs))
    pd={d:round(sum(1 for r in rs if r["day"]==d and r["win"])/max(1,sum(1 for r in rs if r["day"]==d))*100) for d in days}
    print("   按天胜率:",pd)
print("\n注: EV含+1.5分点差. 胜率是他7天数. 价越接近1=越被定价. 频率=每天~n/7个机会.")
