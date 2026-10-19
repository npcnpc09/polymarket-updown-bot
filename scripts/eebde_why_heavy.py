"""WHY does eebde bet HEAVY vs filter (light)? Per btc/eth window: his favorite final $, and market
dynamics: lead toward favorite at 30/60/90s, lead ACCELERATION (strengthening vs fading), choppiness
(direction flips), favorite price, winner. Compare HEAVY (>=2000) vs LIGHT (<800): what distinguishes
them beyond lead level? And does his heavy-bet decision predict outcome better (= a good filter)?"""
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
BN={c:bn(SYM[c],min(sts)-120,max(sts)+400) for c in SYM}
rows=[]
for slug,trs in WT.items():
    coin="btc" if slug.startswith("btc") else "eth"; st=int(slug.split("-")[-1]); d=BN[coin]
    o=d.get(st); cl=d.get(st+240) or d.get(st+300)
    if not o or not cl: continue
    full=defaultdict(float)
    for ts,oc,p,sz,usd in trs: full[oc]+=usd
    fav=max(full,key=full.get); favval=full[fav]
    op=o[0]
    def L(sec):
        pm=d.get(st+sec)
        return (math.log(pm[1]/op)*1e4 if fav=="Up" else -math.log(pm[1]/op)*1e4) if pm else None
    l30,l60,l90=L(0),L(60),L(120)   # 1-min closes ~30/90/150s; use as proxy
    if None in (l30,l60,l90): continue
    accel=l90-l30   # 领先在加强(>0)还是衰减(<0)
    # choppiness: 1-min方向翻转数(前4分钟)
    flips=0; prev=None
    for mm in range(5):
        q=d.get(st+mm*60)
        if q:
            sgn=1 if q[1]>=op else -1
            if prev is not None and sgn!=prev: flips+=1
            prev=sgn
    win=fav==("Up" if cl[1]>=op else "Down")
    rows.append({"betsize":favval,"l90":l90,"accel":accel,"flips":flips,"win":win})
print("窗口:",len(rows),"\n")
heavy=[r for r in rows if r["betsize"]>=2000]; light=[r for r in rows if r["betsize"]<800]
def avg(rs,k): return statistics.mean(r[k] for r in rs) if rs else 0
def wr(rs): return sum(1 for r in rs if r["win"])/len(rs)*100 if rs else 0
print("=== 重注(>=2000) vs 轻注(<800) 对比 ===")
print("              n     领先l90  领先加速度accel  震荡flips  favorite胜率")
print("重注 >=2000  %-4d  %+6.1f   %+8.1f       %.2f       %2.0f%%"%(len(heavy),avg(heavy,"l90"),avg(heavy,"accel"),avg(heavy,"flips"),wr(heavy)))
print("轻注 <800    %-4d  %+6.1f   %+8.1f       %.2f       %2.0f%%"%(len(light),avg(light,"l90"),avg(light,"accel"),avg(light,"flips"),wr(light)))
print("\n=== 控制领先(只看 l90 在 8-20 的窗口), 重注 vs 轻注差在哪 ===")
band=[r for r in rows if 8<=r["l90"]<20]
bh=[r for r in band if r["betsize"]>=2000]; bl=[r for r in band if r["betsize"]<800]
print("  8-20区里 重注: n=%-3d 加速%+.1f 震荡%.2f 胜%2.0f%%"%(len(bh),avg(bh,"accel"),avg(bh,"flips"),wr(bh)))
print("  8-20区里 轻注: n=%-3d 加速%+.1f 震荡%.2f 胜%2.0f%%"%(len(bl),avg(bl,"accel"),avg(bl,"flips"),wr(bl)))
print("\n=== 他的重注决策是不是好过滤? (重注窗口favorite胜率 vs 轻注) ===")
print("  重注favorite胜率 %2.0f%% vs 轻注 %2.0f%%  -> 差%+.0fpp"%(wr(heavy),wr(light),wr(heavy)-wr(light)))
