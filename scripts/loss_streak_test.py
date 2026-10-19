"""Test the user's mean-reversion idea: after N CONSECUTIVE DRY losses, is the NEXT window more likely
to win (mean-revert, exploitable) or LESS (streaky/clustered)? Order btc/eth windows by time; for each,
count the consecutive-loss streak immediately before it; group by streak length -> next-window win%/EV.
Gambler's fallacy if flat (independent); real signal only if win% rises with streak."""
import json,statistics,datetime
ROWS=[]
for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if "won" in r and isinstance(r.get("B"),(int,float)) and r.get("coin")in("btc","eth"):
        try: r["_st"]=int(r["slug"].split("-")[-1])
        except: continue
        ROWS.append(r)
ROWS.sort(key=lambda x:(x["_st"],x["coin"]))
def pnl(r): return 5*(1-r["B"]) if r["won"] else -5*r["B"]
# per window: streak of losses immediately before
groups={0:[],1:[],2:[],3:[]}   # 3 = 3+
streak=0
for r in ROWS:
    g=min(streak,3)
    groups[g].append(r)
    streak = 0 if r["won"] else streak+1
print("总窗口: %d\n"%len(ROWS))
print("=== 前面连续亏N次后, 这一窗的表现 ===")
print("  前置连亏   n     胜率   EV      (验证: 胜率是否随连亏上升=均值回归)")
base_w=sum(1 for r in ROWS if r["won"])/len(ROWS)*100
for g in (0,1,2,3):
    rs=groups[g]
    if not rs: print("  %s 次       n=0"%g); continue
    w=sum(1 for r in rs if r["won"])/len(rs)*100; ev=statistics.mean(pnl(r) for r in rs)
    lbl=("%d"%g) if g<3 else "3+"
    print("  连亏%-3s次  n=%-4d  胜%2.0f%%  EV%+.2f  (基线胜%2.0f%%)"%(lbl,len(rs),w,ev,base_w))
# 也看EV分桶里, 用15m+5m分开会不会不同? 先合并
# 反向核对: 前面连续N次"赢"后的下一窗(看是否对称)
print("\n=== 对照: 前面连续赢N次后 ===")
wg={0:[],1:[],2:[],3:[]}; ws=0
for r in ROWS:
    g=min(ws,3); wg[g].append(r); ws = 0 if not r["won"] else ws+1
for g in (1,2,3):
    rs=wg[g]
    if rs:
        w=sum(1 for r in rs if r["won"])/len(rs)*100; ev=statistics.mean(pnl(r) for r in rs)
        print("  连赢%-3s次后  n=%-4d 胜%2.0f%% EV%+.2f"%(("%d"%g if g<3 else "3+"),len(rs),w,ev))
