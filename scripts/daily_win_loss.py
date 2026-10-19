"""daily_win_loss.py — per-UTC-day win/loss counts + PnL across all live engines, then compare PROFITABLE
days vs LOSING days: is the difference MORE losses, FEWER wins, or BIGGER losses (win/loss-size asymmetry)?"""
import json
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
srcs=[("data/multi_window_engine_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None),
      ("data/multi_window_engine_15m_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None),
      ("data/multi_window_engine_sol_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None),
      ("data/early_taker_probe.jsonl",lambda o:o.get("kind")=="entry" and o.get("won") is not None)]
fills=[]
for f,keep in srcs:
    try:
        for o in (json.loads(l) for l in open(ROOT+"/"+f,encoding="utf-8") if l.strip()):
            if keep(o):
                w=ws_of(o.get("slug",""))
                if w: fills.append({"day":datetime.fromtimestamp(w,timezone.utc).strftime("%m-%d"),"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0)})
    except FileNotFoundError: pass
days={}
for x in fills:
    d=days.setdefault(x["day"],{"n":0,"w":0,"l":0,"pnl":0.0,"wp":0.0,"lp":0.0})
    d["n"]+=1; d["pnl"]+=x["pnl"]
    if x["won"]: d["w"]+=1; d["wp"]+=x["pnl"]
    else: d["l"]+=1; d["lp"]+=x["pnl"]
print(f"{'day':6s} {'fills':5s} {'WON':>4s} {'LOST':>4s} {'win%':>5s} | {'avgWin':>7s} {'avgLoss':>7s} | {'netPnL':>8s}")
for d in sorted(days):
    x=days[d]
    aw=x["wp"]/x["w"] if x["w"] else 0; al=x["lp"]/x["l"] if x["l"] else 0
    tag="GREEN" if x["pnl"]>1 else ("RED" if x["pnl"]<-1 else "flat")
    print(f"{d:6s} {x['n']:5d} {x['w']:4d} {x['l']:4d} {x['w']/x['n']*100:4.0f}% | ${aw:+5.2f} ${al:+6.2f} | ${x['pnl']:+7.2f}  {tag}")
# aggregate green vs red days
G=[days[d] for d in days if days[d]["pnl"]>1]; R=[days[d] for d in days if days[d]["pnl"]<-1]
def agg(D,lab):
    if not D: print(f"  {lab}: none"); return
    n=sum(x["n"] for x in D); w=sum(x["w"] for x in D); l=sum(x["l"] for x in D)
    wp=sum(x["wp"] for x in D); lp=sum(x["lp"] for x in D); pnl=sum(x["pnl"] for x in D)
    print(f"  {lab:18s} days={len(D):2d} fills={n:3d} WON={w:3d} LOST={l:3d} win%={w/n*100:4.0f}% avgWin=${wp/w if w else 0:+.2f} avgLoss=${lp/l if l else 0:+.2f} loss/day={l/len(D):.1f} netPnL=${pnl:+.2f}")
print(f"\n=== GREEN days vs RED days ===")
agg(G,"GREEN days"); agg(R,"RED days")
print("\nREAD: compare LOST/day and win% between green & red days. If red days have ~same win% but more/bigger")
print("losses concentrated -> it's loss CLUSTERS (regime), not a win-rate collapse. That's the whole thesis.")
