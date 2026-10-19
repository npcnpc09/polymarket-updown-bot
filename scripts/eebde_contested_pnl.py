"""eebde's contested-side win/profit probability. Per btc/eth 5m window: his full both-side position
(shares+cost), favorite (max value) + its avg price, winner (binance), and his NET pnl (winner_shares -
total_cost). Split by favorite avg price (contested = low). Report: favorite WIN%, his NET-PROFIT%, avg
net $. Key Q: on contested favorites (avg<0.5), does his hedge keep him net-positive even at ~50% fav-win?"""
import json,re,httpx,math,statistics
from collections import defaultdict
EF="data/eebde_history_7d.jsonl"
POS=defaultdict(lambda:defaultdict(lambda:[0.0,0.0]))  # slug->outcome->[shares,cost]
for ln in open(EF,encoding="utf-8"):
    ln=ln.strip()
    if not ln: continue
    try: r=json.loads(ln)
    except: continue
    if r.get("type")!="TRADE" or (r.get("side") or "").upper()!="BUY": continue
    m=re.match(r"(btc|eth)-updown-5m-(\d+)",r.get("slug","") or "")
    if not m or r.get("outcome") not in ("Up","Down"): continue
    POS[r["slug"]][r["outcome"]][0]+=(r.get("size",0) or 0); POS[r["slug"]][r["outcome"]][1]+=(r.get("usdcSize",0) or 0)
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}; sts=[int(s.split("-")[-1]) for s in POS]
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
rows=[]
for slug,p in POS.items():
    w=winner(slug)
    if not w: continue
    up=p.get("Up",[0,0]); dn=p.get("Down",[0,0])
    if up[1]+dn[1]<50: continue
    fav="Up" if up[1]>=dn[1] else "Down"
    favsh,favco=p[fav]; favpx=favco/favsh if favsh>0 else 0
    wsh=up[0] if w=="Up" else dn[0]; cost=up[1]+dn[1]
    net=wsh-cost
    rows.append({"favpx":favpx,"favwin":fav==w,"net":net,"netwin":net>0,"cost":cost})
print("窗口:",len(rows),"\n")
def stat(rs,lab):
    if not rs: print("  %-22s 0"%lab); return
    fw=sum(1 for r in rs if r["favwin"])/len(rs)*100
    nw=sum(1 for r in rs if r["netwin"])/len(rs)*100
    anet=statistics.mean(r["net"] for r in rs); acost=statistics.mean(r["cost"] for r in rs)
    print("  %-22s n=%-4d favorite胜%2.0f%% | 他净盈利%%=%2.0f%% 均净$%+6.0f (均投入$%.0f, ROI%+.1f%%)"%(
        lab,len(rs),fw,nw,anet,acost,anet/acost*100 if acost else 0))
print("按他 favorite 均价(=把握度) 分: favorite胜率 / 他净盈利概率 / 均净额\n")
stat([r for r in rows if r["favpx"]<0.45],"争议<0.45")
stat([r for r in rows if 0.45<=r["favpx"]<0.55],"争议0.45-0.55")
stat([r for r in rows if 0.55<=r["favpx"]<0.65],"偏弱0.55-0.65")
stat([r for r in rows if 0.65<=r["favpx"]<0.8],"中0.65-0.8")
stat([r for r in rows if r["favpx"]>=0.8],"强>=0.8")
print()
stat([r for r in rows if r["favpx"]<0.6],"=> 所有争议(<0.6)")
stat(rows,"=> 全部")
