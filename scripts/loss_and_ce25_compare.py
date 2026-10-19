"""(1) Characterize our LIVE early-taker losers vs winners (band/lead/offset/coin/vol). (2) For each of our
live entry windows, find what ce25 did in the SAME window (same slug): did he buy, same side, what price?
Answers 'are our orders like ce25's?' — overlap, same-side rate, his price vs ours."""
import json,os,httpx,statistics
from collections import defaultdict
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows=[json.loads(l) for l in open(os.path.join(ROOT,"data","early_taker_probe.jsonl"),encoding="utf-8")]
live=[r for r in rows if r.get("live") and r.get("won") is not None]
W=[r for r in live if r["won"]]; L=[r for r in live if not r["won"]]
print("=== LIVE 真盘 %d笔: %d胜 / %d负 ==="%(len(live),len(W),len(L)))
def avg(rs,k):
    v=[r[k] for r in rs if r.get(k) is not None]; return statistics.mean(v) if v else float('nan')
print("\n--- 赢家 vs 输家 特征均值 ---")
print("  %-10s 胜率n 均价  |lead| offset  vol"%"")
for nm,rs in (("赢家",W),("输家",L)):
    print("  %-10s n=%-3d %.3f  %.1f   %4.0fs  %.1f"%(nm,len(rs),avg(rs,"paid"),avg([{"a":abs(r["lead"])} for r in rs],"a"),avg(rs,"offset"),avg(rs,"btc_vol")))
print("\n--- 每笔输单明细 (找共性) ---")
for r in sorted(L,key=lambda x:x["offset"]):
    print("  %-26s %-4s 付%.3f lead%+5.1f cb%-6s @%3ds vol%.1f band%s pnl%.2f"%(
        r["slug"],r["side"],r["paid"],r["lead"],str(r.get("cb_lead")),r["offset"],r.get("btc_vol") or 0,r["band"],r["pnl"]))
# 输单按时点/价格档归类
print("\n--- 输单分布 ---")
for lo,hi,nm in ((0,60,"<60s"),(60,180,"60-180s")):
    sub=[r for r in L if lo<=r["offset"]<hi]; tot=[r for r in live if lo<=r["offset"]<hi]
    if tot: print("  %-8s 输%d/%d (%.0f%%输)"%(nm,len(sub),len(tot),len(sub)/len(tot)*100))
for b in ("0.5-0.65","0.65-0.75","0.75-0.85"):
    sub=[r for r in L if r["band"]==b]; tot=[r for r in live if r["band"]==b]
    if tot: print("  %-10s 输%d/%d (%.0f%%输)"%(b,len(sub),len(tot),len(sub)/len(tot)*100))

# ===== ce25 对比 =====
print("\n\n=== 对比 ce25: 我们的每个入场窗口, ce25 做了什么 ===")
CE="0xcE25E214D5cfE4f459cf67F08DF581885AAE7Fdc"
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
A=[]
for off in range(0,4000,500):
    try: a=c.get("https://data-api.polymarket.com/activity",params={"user":CE,"limit":500,"offset":off}).json()
    except: break
    if not isinstance(a,list) or not a: break
    A+=[x for x in a if x.get("type")=="TRADE" and (x.get("side") or "").upper()=="BUY"]
    if len(a)<500: break
ce=defaultdict(list)  # slug -> [(outcome,price,size)]
for x in A:
    if x.get("slug"): ce[x["slug"]].append((x.get("outcome"),x.get("price") or 0,x.get("size") or 0))
both=0; sameside=0; ourpx=[]; hispx=[]; he_absent=0; details=[]
for r in live:
    ch=ce.get(r["slug"])
    if not ch: he_absent+=1; continue
    both+=1
    # ce25 net side by value
    val=defaultdict(float)
    for oc,p,s in ch: val[oc]+=p*s
    his_side=max(val,key=val.get); his_px=statistics.mean([p for oc,p,s in ch if oc==his_side])
    same=(his_side==r["side"])
    if same: sameside+=1; ourpx.append(r["paid"]); hispx.append(his_px)
    details.append((r["slug"],r["side"],r["paid"],his_side,round(his_px,3),same,r["won"]))
print("我们 live 入场 %d 个窗口: ce25 也在场 %d 个, 缺席 %d 个"%(len(live),both,he_absent))
if both:
    print("  同窗时同向率: %d/%d = %.0f%%"%(sameside,both,sameside/both*100))
    if ourpx: print("  同向时: 我们均价 %.3f vs ce25均价 %.3f (差 %+.1fc, 负=我们更贵)"%(statistics.mean(ourpx),statistics.mean(hispx),(statistics.mean(ourpx)-statistics.mean(hispx))*100))
    print("\n  --- 共同在场的窗口明细 ---")
    for slug,os_,op,hs,hp,sm,won in details[:25]:
        print("    %-26s 我们%-4s@%.3f | ce25%-4s@%.3f %s %s"%(slug,os_,op,hs,hp,"同向" if sm else "反向!","赢" if won else "输"))
