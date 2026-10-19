"""check_stream_starve.py — is the eth-pause STARVING its own recovery? roll10 reads the combined (taker+zmaker
FILLED) stream. Pausing eth removes eth's (winning) fills -> stream gets sparse -> the 2 old losses don't age
out -> roll10 stays >=2 -> eth stays paused. Show the last-10 combined fills + the 2 losses' ages + recent
fill density (with vs without eth)."""
import json, time
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
now=int(time.time())
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
comb=[]
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl",encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None:
        w=ws_of(o.get("slug",""))
        if w: comb.append({"ws":w,"coin":o.get("coin"),"won":bool(o["won"]),"src":"zmaker"})
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8") if l.strip()):
    if o.get("kind")=="entry" and o.get("won") is not None:
        w=ws_of(o.get("slug",""))
        if w: comb.append({"ws":w,"coin":o.get("coin"),"won":bool(o["won"]),"src":"taker"})
comb.sort(key=lambda x:x["ws"])
last10=comb[-10:]
print("=== last 10 COMBINED fills (what roll10 sees) ===")
for f in last10:
    t=datetime.fromtimestamp(f["ws"],timezone.utc).strftime("%m-%d %H:%M"); age=(now-f["ws"])/60
    print(f"  {t} ({age:4.0f}min ago) {f['coin']:3s} {f['src']:6s} {'WON' if f['won'] else 'LOST'}")
losses=[f for f in last10 if not f["won"]]
print(f"\n  losses in last-10: {len(losses)} (roll10={len(losses)})")
for f in losses:
    print(f"    {f['coin']} {f['src']} LOST, {(now-f['ws'])/60:.0f} min ago")
# fill density last 3h: with eth vs without
recent=[f for f in comb if f["ws"]>=now-3*3600]
eth_recent=[f for f in recent if f["coin"]=="eth"]
print(f"\n=== combined fill density, last 3h ===")
print(f"  total combined fills: {len(recent)} ({len(recent)/3:.1f}/hr)")
print(f"  of which eth: {len(eth_recent)} -- these would normally age the window faster but are now mostly PAUSED")
print(f"  span of last-10: {(last10[-1]['ws']-last10[0]['ws'])/60:.0f} min")
print("\nREAD: if the 2 losses are OLD (>60min) and the last-10 spans a long time / few eth fills -> the pause is")
print("starving the stream so roll10 won't drop. Fix: detect regime from BTC-only stream (never starved, btc")
print("leads eth) OR count skipped-eth outcomes in roll10 OR time-based eth resume.")
