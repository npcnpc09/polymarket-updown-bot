"""drawdown_avoidable.py — of the recent ~$26 drawdown, how much was AVOIDABLE by 'don't open in the bad phase'?
Split each loss by the combined roll10 AT THE TIME: roll10<2 = breaker NOT armed = we didn't know it was a bad
phase yet = UNAVOIDABLE (the first losses ARE the detection signal). roll10>=2 = already armed = we knew =
avoidable-by-pausing (but already de-risked to 5sh)."""
import json
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
PEAK_TS=1781971010  # the ~$330 peak
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
losses=[]
for f,keep in (("data/multi_window_engine_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None),
               ("data/early_taker_probe.jsonl",lambda o:o.get("kind")=="entry" and o.get("won") is not None),
               ("data/multi_window_engine_sol_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None)):
    for o in (json.loads(l) for l in open(ROOT+"/"+f,encoding="utf-8") if l.strip()):
        if keep(o):
            w=ws_of(o.get("slug",""))
            if w and w>=PEAK_TS-300 and not o["won"]:
                losses.append({"ws":w,"coin":o.get("coin"),"pnl":float(o.get("pnl",0) or 0),"roll10":o.get("roll10"),"sh":o.get("sh")})
losses.sort(key=lambda x:x["ws"])
pre=[l for l in losses if l["roll10"] is None or l["roll10"]<2]   # breaker not armed = undetected
post=[l for l in losses if l["roll10"] is not None and l["roll10"]>=2]  # armed = detected, already de-risked
from datetime import datetime,timezone
print(f"losses since peak ($330): {len(losses)}, total ${sum(l['pnl'] for l in losses):+.2f}\n")
print(f"{'time':12s} {'coin':4s} {'sh':3s} {'pnl':7s} {'roll10':6s} {'detected?':10s}")
for l in losses:
    t=datetime.fromtimestamp(l["ws"],timezone.utc).strftime("%m-%d %H:%M")
    det="ARMED(knew)" if (l["roll10"] is not None and l["roll10"]>=2) else "not armed(blind)"
    print(f"{t:12s} {str(l['coin']):4s} {str(l['sh']):3s} ${l['pnl']:6.2f} {str(l['roll10']):6s} {det}")
print(f"\n  PRE-detection (roll10<2, BLIND -> UNAVOIDABLE by 'pause in bad phase'): {len(pre)} losses, ${sum(l['pnl'] for l in pre):+.2f}")
print(f"  POST-detection (roll10>=2, knew -> already 5sh; pausing saves a bit more): {len(post)} losses, ${sum(l['pnl'] for l in post):+.2f}")
print("\nREAD: the PRE-detection chunk is what you CANNOT avoid by 'not opening in the bad phase' -- at that moment")
print("there was no signal it was a bad phase (the breaker arms only AFTER >=2 losses). Those first losses ARE")
print("the detection cost. Only the POST chunk is avoidable, and it's already de-risked to 5sh.")
