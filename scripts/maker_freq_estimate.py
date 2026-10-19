"""Estimate maker orders/day under different entry gates, from DRY accel-labeled history.
maker currently = btc/eth, lead>=5 at checkpoints, 5m+15m, ~1.4 fills/window (31 fills/23 win observed).
Question: adding accel>=10 -> how many windows/day, hence orders/day."""
import json
R=[]
for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if "won" not in r or not isinstance(r.get("accel"),(int,float)): continue
    try: st=int(r["slug"].split("-")[-1])
    except: continue
    r["_st"]=st; R.append(r)
be=[r for r in R if r.get("coin")in("btc","eth")]
if not be: print("无btc/eth accel数据"); raise SystemExit
span=(max(r["_st"] for r in be)-min(r["_st"] for r in be))/86400.0
print("btc/eth accel-标签数据跨度: %.2f 天 (%d窗)\n"%(span,len(be)))
def perday(cond,lbl):
    n=sum(1 for r in be if cond(r))
    pd=n/span if span>0 else 0
    # maker fires on 5m+15m; DRY here already includes both. ~1.4 orders/window (scale-in)
    print("  %-32s 窗口 %3d  → %5.1f 窗/天  ≈ %5.1f 单/天(×1.4)"%(lbl,n,pd,pd*1.4))
print("=== 不同入场门槛下的频率 ===")
perday(lambda r: abs(r.get("lead",0)or 0)>=5, "lead>=5 (当前maker条件)")
perday(lambda r: abs(r.get("lead",0)or 0)>=5 and r["accel"]>0, "lead>=5 & accel>0")
perday(lambda r: abs(r.get("lead",0)or 0)>=5 and r["accel"]>=10, "lead>=5 & accel>=10")
perday(lambda r: abs(r.get("lead",0)or 0)>=8 and r["accel"]>=10, "lead>=8 & accel>=10")
perday(lambda r: abs(r.get("lead",0)or 0)>=8 and (r.get("max_lead")or 0)>=15 and r["accel"]>=10, "自营全条件 & accel>=10")
print("\n注:lead取entry(~167s)的值,maker实际在30-120s任一检查点lead>=5就挂,会更宽松→上面是偏低估计")
