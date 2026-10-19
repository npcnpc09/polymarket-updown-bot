"""Compare our DRY self-taker entries vs eebde (data/divergence.jsonl): which windows WE entered did
eebde NOT load our side / do OPPOSITE, and how did WE fare. = is 'eebde opposite' a loss predictor."""
import json,datetime
R=[]
for l in open("data/divergence.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: R.append(json.loads(l))
    except: pass
def ev(rs): return sum((5*(1-r["B"]) if r["won"] else -5*r["B"]) for r in rs)/len(rs) if rs else 0
def wr(rs): return sum(1 for r in rs if r["won"])/len(rs)*100 if rs else 0
def line(rs,lbl):
    if not rs: print("  %-26s n=0"%lbl); return
    print("  %-26s n=%-3d 胜%2.0f%% EV%+.2f 总$%+.1f"%(lbl,len(rs),wr(rs),ev(rs),sum((5*(1-r["B"]) if r["won"] else -5*r["B"]) for r in rs)))
opp=[r for r in R if r["cat"]=="opposite"]
same=[r for r in R if r["cat"]!="opposite"]
print("=== 我们入场 vs eebde (n=%d, 7h) ==="%len(R))
line(R,"全部")
line(same,"他也押我们这侧(轻/重)")
line(opp,"他押反方向 ***")
print("\n=== 他押反 vs 同向 (核心: 押反是不是亏的预警) ===")
print("  同向: 胜%.0f%% EV%+.2f"%(wr(same),ev(same)))
print("  押反: 胜%.0f%% EV%+.2f  → 差 %+.0fpp"%(wr(opp),ev(opp),wr(opp)-wr(same)))
print("\n=== 他押反的窗口逐个 (我们下了他反向) ===")
print("  时间   我侧 赢亏 我lead 他$本侧 他$反侧 his_lp(前几分钟)")
for r in sorted(opp,key=lambda x:x["slug"]):
    st=int(r["slug"].split("-")[-1]); hm=datetime.datetime.utcfromtimestamp(st).strftime("%H:%M")
    lp="/".join(str(int(x)) if x is not None else "·" for x in (r.get("lp") or [])[:4])
    print("  %s %-4s %s lead%+.0f 本$%4.0f 反$%4.0f | %s"%(hm,r["side"],"赢" if r["won"] else "亏",r.get("lead",0),r.get("us",0),r.get("uo",0),lp))
