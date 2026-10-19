"""eth_recent_only.py — ETH only, recent days only (per-day PnL/win%/G, cell vs taker). No older data."""
import json
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
fills=[]
for f,eng,keep in (("data/multi_window_engine_live.jsonl","cell",lambda o:o.get("filled") is True and o.get("won") is not None),
                   ("data/early_taker_probe.jsonl","taker",lambda o:o.get("kind")=="entry" and o.get("won") is not None)):
    for o in (json.loads(l) for l in open(ROOT+"/"+f,encoding="utf-8") if l.strip()):
        if keep(o) and o.get("coin")=="eth":
            w=ws_of(o.get("slug",""))
            if w:
                sh=float(o.get("sh",5) or 5); B=float(o.get("B") or o.get("paid") or 0.8)
                fills.append({"ws":w,"eng":eng,"day":datetime.fromtimestamp(w,timezone.utc).strftime("%m-%d"),"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),"risk":sh*B})
days=sorted(set(f["day"] for f in fills))[-6:]
print("=== ETH only, last 6 days (per day) ===")
print(f"{'day':6s} {'fills':5s} {'W':>3s} {'L':>3s} {'win%':>5s} {'PnL':>8s} {'G':>7s}")
for d in days:
    s=[f for f in fills if f["day"]==d]; w=sum(1 for f in s if f["won"]); p=sum(f["pnl"] for f in s); r=sum(f["risk"] for f in s)
    print(f"{d:6s} {len(s):5d} {w:3d} {len(s)-w:3d} {w/len(s)*100:4.0f}% ${p:+7.2f} {p/r*100 if r else 0:+6.2f}%")
recent=[f for f in fills if f["day"] in days[-3:]]
w=sum(1 for f in recent if f["won"]); p=sum(f["pnl"] for f in recent); r=sum(f["risk"] for f in recent)
print(f"\nlast 3 days: {len(recent)} fills, win% {w/len(recent)*100:.0f}, PnL ${p:+.2f}, G {p/r*100 if r else 0:+.2f}%")
for eng in ("cell","taker"):
    s=[f for f in recent if f["eng"]==eng]
    if s:
        w=sum(1 for f in s if f["won"]); p=sum(f["pnl"] for f in s); r=sum(f["risk"] for f in s)
        print(f"  eth {eng:5s} last3d: n={len(s):3d} win% {w/len(s)*100:.0f} PnL ${p:+.2f} G {p/r*100 if r else 0:+.2f}%")
