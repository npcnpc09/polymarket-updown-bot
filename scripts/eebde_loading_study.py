"""What makes eebde CONTINUE loading (turn a position heavy)? Pull his recent per-trade activity, bucket
by window, and for each window reconstruct his cumulative-load curve + the underlying lead trajectory
(toward his favorite). Compare windows he ended HEAVY (>1500) vs LIGHT: does he keep adding only when the
lead PERSISTS/STRENGTHENS, and stop (stay light) when it wobbles? = his continue-heavy judgment."""
import json,math,httpx,statistics
from collections import defaultdict
EEB="0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
ACT=[]
for off in range(0,3000,500):
    try: a=c.get("https://data-api.polymarket.com/activity",params={"user":EEB,"limit":500,"offset":off}).json()
    except: break
    if not isinstance(a,list) or not a: break
    ACT+=[x for x in a if x.get("type")=="TRADE" and (x.get("side","")or"").upper()=="BUY"]
    if len(a)<500: break
HB=defaultdict(list)
for x in ACT:
    s=x.get("slug","")
    if "-updown-5m-" in s and (s.startswith("btc")or s.startswith("eth")): HB[s].append(x)
print("覆盖窗口: %d (他最近活动)"%len(HB))
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
def kl(sym,st):
    try:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":(st-60)*1000,"endTime":(st+360)*1000,"limit":12}).json()
        return {int(x[0]//1000):float(x[1]) for x in k}
    except: return {}
rows=[]
for slug,trs in HB.items():
    coin="btc" if slug.startswith("btc") else "eth"; st=int(slug.split("-")[-1])
    by=defaultdict(float)
    for t in trs: by[t.get("outcome")]+=(t.get("usdcSize") or 0)
    if not by: continue
    fav=max(by,key=by.get); favcum=by[fav]
    d=kl(SYM[coin],st); op=d.get(st)
    if not op: continue
    def lead(sec):  # toward his favorite
        p=d.get(st+sec);
        if not p: return None
        L=math.log(p/op)*1e4; return L if fav=="Up" else -L
    lp=[lead(s) for s in (0,60,120,180,240)]
    favtr=sorted([t for t in trs if t.get("outcome")==fav],key=lambda x:x["timestamp"])
    # 加仓时机: 首/末加仓offset, 加仓笔数
    offs=[t["timestamp"]-st for t in favtr]
    # lead是否单调走强(从60到180)
    valid=[x for x in lp[1:4] if x is not None]
    strengthen = (len(valid)>=2 and valid[-1]>=valid[0])
    rows.append({"slug":slug,"fav":fav,"favcum":favcum,"nfav":len(favtr),
        "first":min(offs) if offs else None,"last":max(offs) if offs else None,"lp":lp,"strengthen":strengthen,
        "peaklead":max((x for x in lp if x is not None),default=0),"minlead":min((x for x in lp if x is not None),default=0)})
heavy=[r for r in rows if r["favcum"]>=1500]; light=[r for r in rows if r["favcum"]<1500]
def fmtlp(lp): return "/".join((("%+.0f"%x) if x is not None else "·") for x in lp)
print("\n=== 重仓窗(>=1500, n=%d) 的加仓 + lead轨迹 ==="%len(heavy))
print("时间线: 他favorite $累计 | 加仓笔 首/末s | lead 0/1/2/3/4m")
for r in sorted(heavy,key=lambda x:-x["favcum"])[:12]:
    print("  %s $%5.0f 笔%-3d %3.0f/%-3.0f | %s %s"%(r["slug"][-12:],r["favcum"],r["nfav"],r["first"] or 0,r["last"] or 0,fmtlp(r["lp"]),"走强" if r["strengthen"] else "wobble"))
def agg(rs,lbl):
    if not rs: return
    print("  %-12s n=%-3d 平均favcum$%5.0f 平均加仓笔%.1f 末加仓%.0fs lead走强占%.0f%% 平均峰值lead%+.1f 平均谷lead%+.1f"%(
        lbl,len(rs),statistics.mean(r["favcum"] for r in rs),statistics.mean(r["nfav"] for r in rs),
        statistics.mean(r["last"] or 0 for r in rs),sum(1 for r in rs if r["strengthen"])/len(rs)*100,
        statistics.mean(r["peaklead"] for r in rs),statistics.mean(r["minlead"] for r in rs)))
print("\n=== 重仓 vs 轻仓: 他继续加重注的判断依据 ===")
agg(heavy,"重仓>=1500"); agg(light,"轻仓<1500")
