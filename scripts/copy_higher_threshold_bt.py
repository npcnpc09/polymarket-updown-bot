"""Backtest HIGHER copy thresholds ($1000/1500/2000/3000) — does waiting for stronger confirmation
(he keeps loading) avoid the weak-conviction losses (final<1500) without killing EV? For each btc/eth
window in eebde's 7d history: copy when his FAVORITE cumulative first crosses each threshold; record his
price there (taker pays +1.5c spread), win (binance). Report freq / win% / EV / avg-loss / how many of
the OLD $1000 losers get excluded by the higher bar."""
import json,re,httpx,math
from collections import defaultdict
import statistics
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
def winner(slug):
    c="btc" if slug.startswith("btc") else "eth"; st=int(slug.split("-")[-1]); d=BN[c]
    o=d.get(st) or d.get(st+1); cl=d.get(st+240) or d.get(st+300)
    return ("Up" if cl[1]>=o[0] else "Down") if (o and cl) else None
SPREAD=0.015; SH=5; THR=[1000,1500,2000,3000]
res={t:[] for t in THR}
total_windows=0
for slug,trs in WT.items():
    w=winner(slug)
    if not w: continue
    total_windows+=1
    trs.sort(key=lambda x:x[0]); cum=defaultdict(float); hit={t:False for t in THR}
    for ts,o,p,sz in trs:
        cum[o]+=p*sz; fav=max(cum,key=cum.get)
        for t in THR:
            if not hit[t] and cum[fav]>=t:
                hit[t]=True
                ask=min(p+SPREAD,0.98)
                res[t].append({"win":fav==w,"ask":ask,"pnl":(1-ask)*SH if fav==w else -ask*SH})
print("总可结算窗口:",total_windows,"\n")
print("%-8s %6s %7s %7s %9s %9s %9s"%("门槛$","跟单数","占比%","胜率","均价","EV/单","平均亏损"))
for t in THR:
    rs=res[t]
    if not rs: continue
    n=len(rs); wr=sum(1 for r in rs if r["win"])/n*100
    ev=sum(r["pnl"] for r in rs)/n
    apx=statistics.mean(r["ask"] for r in rs)
    losses=[r["pnl"] for r in rs if not r["win"]]
    avgloss=statistics.mean(losses) if losses else 0
    print("$%-7d %6d %6.0f%% %6.0f%% %9.3f %+9.2f %+9.2f"%(t,n,n/total_windows*100,wr,apx,ev,avgloss))
print("\n注: 门槛越高=频率越低、胜率越高、但均价越贵(单笔亏越大). EV含+1.5分taker点差.")
