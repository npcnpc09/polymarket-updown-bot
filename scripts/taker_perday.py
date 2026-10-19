"""taker_perday.py — taker per-UTC-day PnL + cumulative, last ~8 days. Is the recent combined taker PnL negative?"""
import json
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
tk=[]
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8") if l.strip()):
    if o.get("kind")=="entry" and o.get("won") is not None:
        w=ws_of(o.get("slug",""))
        if w: tk.append({"day":datetime.fromtimestamp(w,timezone.utc).strftime("%m-%d"),"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0)})
days={}
for x in tk:
    d=days.setdefault(x["day"],{"n":0,"w":0,"pnl":0.0})
    d["n"]+=1; d["pnl"]+=x["pnl"]
    if x["won"]: d["w"]+=1
allday=sorted(days)
print(f"{'day':6s} {'fills':5s} {'win%':>5s} {'dayPnL':>8s} {'cumPnL':>8s}")
cum=0.0
for d in allday:
    x=days[d]; cum+=x["pnl"]
    print(f"{d:6s} {x['n']:5d} {x['w']/x['n']*100:4.0f}% ${x['pnl']:+7.2f} ${cum:+7.2f}")
last5=allday[-5:]
s5=sum(days[d]["pnl"] for d in last5); s3=sum(days[d]["pnl"] for d in allday[-3:])
print(f"\nlast 5 days ({last5[0]}~{last5[-1]}): ${s5:+.2f}")
print(f"last 3 days ({allday[-3]}~{allday[-1]}): ${s3:+.2f}")
print(f"lifetime: ${sum(days[d]['pnl'] for d in allday):+.2f}")
