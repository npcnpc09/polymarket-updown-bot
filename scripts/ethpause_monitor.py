"""ethpause_monitor.py — forward monitor of the deployed eth-pause: how many eth entries did it SKIP during
armed periods, and (counterfactually, REAL PM settle) how many would have LOST vs WON? Net saved = avoided
loss$ - forgone win$. Reads both engines' tracked eth_pause skips (zmaker s.skips + taker spike rows)."""
import json
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
rows=[]
# zmaker: rows tagged {"skipped":"eth_pause", would_win, would_pnl}
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl",encoding="utf-8") if l.strip()):
    if o.get("skipped")=="eth_pause" and o.get("would_win") is not None:
        rows.append({"eng":"cell","won":bool(o["would_win"]),"wp":float(o.get("would_pnl",0) or 0),"slug":o.get("slug")})
# taker: spike rows reason="eth_pause" with would_win
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8") if l.strip()):
    if o.get("kind")=="spike" and o.get("reason")=="eth_pause" and o.get("would_win") is not None:
        # taker would_pnl ~ 5*(1-paid) win / -5*ask0 loss; approximate at ask0
        ask=o.get("ask0") or 0.82; wp=5*(1-ask) if o["would_win"] else -5*ask
        rows.append({"eng":"taker","won":bool(o["would_win"]),"wp":wp,"slug":o.get("slug")})
n=len(rows)
if n==0:
    print("eth-pause skips resolved so far: 0  (just deployed 2026-06-21 — accrues as eth gets skipped in armed periods)")
    print("re-run this after some armed/cooling periods to see avoided losses vs forgone wins.")
else:
    losses=[r for r in rows if not r["won"]]; wins=[r for r in rows if r["won"]]
    avoided=-sum(r["wp"] for r in losses); forgone=sum(r["wp"] for r in wins)
    print(f"=== eth-pause skips resolved: {n} ===")
    print(f"  AVOIDED losses: {len(losses):3d}  (saved ${avoided:+.2f})")
    print(f"  forgone wins:   {len(wins):3d}  (gave up ${forgone:+.2f})")
    print(f"  NET saved (avoided loss - forgone win) = ${avoided-forgone:+.2f}")
    print(f"  hit rate of the skip (% that would have lost) = {len(losses)/n*100:.0f}%")
    for r in rows[-10:]:
        print(f"    {r['eng']:5s} {r['slug']} would_{'LOSE' if not r['won'] else 'win'} (${r['wp']:+.2f})")
