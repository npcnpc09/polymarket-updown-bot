"""cell_streak.py — longest consecutive-WIN streak for the cell (z-maker 0.90-0.95 fills), time-ordered."""
import json
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
cell=[]
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl",encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None and o.get("B") and 0.90<=o["B"]<0.96:
        w=ws_of(o.get("slug",""))
        if w: cell.append({"ws":w,"won":bool(o["won"])})
cell.sort(key=lambda x:x["ws"])
def t(ws): return datetime.fromtimestamp(ws,timezone.utc).strftime("%m-%d %H:%M")
best=0; cur=0; best_end=None; cur_start=None; runs=[]
for c in cell:
    if c["won"]:
        if cur==0: cur_start=c["ws"]
        cur+=1
        if cur>best: best=cur; best_end=c["ws"]; best_start=cur_start
    else:
        if cur>0: runs.append((cur,cur_start))
        cur=0
if cur>0: runs.append((cur,cur_start))
w=sum(1 for c in cell if c["won"])
print(f"cell fills total: {len(cell)}  wins {w}  losses {len(cell)-w}  win% {w/len(cell)*100:.1f}")
print(f"\nLONGEST consecutive-win streak: {best} wins")
print(f"  from {t(best_start)} to {t(best_end)} UTC")
print(f"\nall win-streaks >= 20 (length, started):")
for L,st in sorted(runs,reverse=True):
    if L>=20: print(f"  {L:3d} wins, started {t(st)}")
print(f"\ntotal losses (streak-breakers): {len(cell)-w} at:")
for i,c in enumerate(cell):
    if not c["won"]: print(f"  {t(c['ws'])}")
