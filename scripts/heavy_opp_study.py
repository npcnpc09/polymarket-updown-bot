"""Study HEAVY-opposite windows (eebde put big $ AGAINST our momentum side). Key question: what did he
see that our raw-underlying-lead signal missed? First lever: did the PM PRICE already disagree with our
lead? Our entry B = PM price of OUR side; B<0.5 => PM market priced our side as UNDERDOG despite the
underlying leading our way => eebde (and the market) followed PM-implied prob, not raw momentum.
Also: lead path (did underlying reverse?) and his $ split."""
import json,datetime
R=[]
for l in open("data/divergence.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: R.append(json.loads(l))
    except: pass
# heavy opposite: his opposite $ >= 100 AND clearly > his our-side $
heavy=[r for r in R if r["cat"]=="opposite" and r.get("uo",0)>=80 and r.get("uo",0)>r.get("us",0)*2]
allopp=[r for r in R if r["cat"]=="opposite"]
print("全部押反: %d, 其中重金(反$>=80且>本侧2x): %d\n"%(len(allopp),len(heavy)))
print("=== 重金押反窗口深挖 ===")
print("时间   我侧 赢亏 我lead 我B(PM对我侧定价) PM是否站他那边 | 他本$/反$ | lead路径")
for r in sorted(heavy,key=lambda x:-x.get("uo",0)):
    st=int(r["slug"].split("-")[-1]); hm=datetime.datetime.utcfromtimestamp(st).strftime("%m-%d %H:%M")
    B=r.get("B",0); pm_against=("是,PM定我侧为劣势" if B<0.5 else ("中性~0.5" if B<0.6 else "否,PM也站我侧"))
    lp="/".join(str(int(x)) if x is not None else "·" for x in (r.get("lp") or []))
    print(" %s %-4s %s lead%+.0f  B=%.2f  %s | 本$%.0f/反$%.0f | %s"%(
        hm,r["side"],"赢" if r["won"] else "亏",r.get("lead",0),B,pm_against,r.get("us",0),r.get("uo",0),lp))
print("\n=== 对照: 全部押反窗口的 B 分布 (PM定价 vs 我们的lead) ===")
import statistics
for grp,lbl in ((heavy,"重金押反"),([r for r in allopp if r not in heavy],"微弱偏反")):
    if not grp: continue
    Bs=[r.get("B",0) for r in grp]; lo=[r for r in grp if r.get("B",1)<0.5]
    print("  %s n=%d: 平均B=%.2f, 其中B<0.5(PM站他那边)的占 %d/%d, 胜率%.0f%%"%(
        lbl,len(grp),statistics.mean(Bs),len(lo),len(grp),sum(1 for r in grp if r["won"])/len(grp)*100))
