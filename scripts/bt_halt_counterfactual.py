"""bt_halt_counterfactual.py — IF the engines had stayed OPEN during the overnight halt, what P&L?
Halt began ~2026-06-24 23:30Z ($377.77 stop fire). The 15m DRY collectors kept logging would-be fills with
real settle outcomes -> direct counterfactual for the 15m engine. 5m taker/cell DRY (alt_exec_dry.jsonl) is
stale (6/17) so 5m is reconstructed separately. Here: sum 15m DRY taker_pnl + maker_pnl over the halt window,
broken out by hour, so we can see if staying open would have made or lost money.
Honest caveat: settle via the DRY's own settle_bps (binance proxy, not Chainlink) — directional, tight calls noisy."""
import json
from collections import defaultdict
from datetime import datetime, timezone
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
HALT=1782349800  # ~2026-06-24 23:30Z
def load(fn):
    out=[]
    for l in open(ROOT+"/data/"+fn,encoding="utf-8"):
        if not l.strip(): continue
        try:o=json.loads(l)
        except:continue
        ts=o.get("ts")
        if ts is None or ts<HALT: continue
        if o.get("won") is None: continue
        out.append(o)
    return out
for fn in ("alt_exec_dry_15m_regime.jsonl","alt_exec_dry_15m.jsonl"):
    rows=load(fn)
    if not rows:
        print(f"\n=== {fn}: no rows in halt window ===" ); continue
    rows.sort(key=lambda x:x["ts"])
    tk=sum(float(r.get("taker_pnl",0) or 0) for r in rows)
    mk=sum(float(r.get("maker_pnl",0) or 0) for r in rows if r.get("maker_filled"))
    nmk=sum(1 for r in rows if r.get("maker_filled"))
    w=sum(1 for r in rows if r.get("won"))
    span=f"{datetime.fromtimestamp(rows[0]['ts'],tz=timezone.utc).strftime('%m-%d %H:%M')} -> {datetime.fromtimestamp(rows[-1]['ts'],tz=timezone.utc).strftime('%H:%M')}"
    print(f"\n=== {fn} | halt window {span} ===")
    print(f"  windows={len(rows)} win%={w/len(rows)*100:.1f}  TAKER pnl=${tk:+.2f}  MAKER pnl(filled {nmk})=${mk:+.2f}")
    # by hour
    byh=defaultdict(list)
    for r in rows: byh[datetime.fromtimestamp(r["ts"],tz=timezone.utc).strftime("%m-%d %H")].append(r)
    print(f"  {'hour':9s} {'n':>3s} {'win%':>5s} {'taker$':>8s} {'maker$':>8s}")
    for h in sorted(byh):
        s=byh[h]; ww=sum(1 for r in s if r.get("won"))
        t=sum(float(r.get('taker_pnl',0) or 0) for r in s)
        m=sum(float(r.get('maker_pnl',0) or 0) for r in s if r.get('maker_filled'))
        print(f"  {h:9s} {len(s):>3d} {ww/len(s)*100:>5.1f} {t:>+8.2f} {m:>+8.2f}")
