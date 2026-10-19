"""loss_clusters.py — lay out recent REAL losses chronologically across all live engines, and group them
into CLUSTERS (losses within GAP_MIN minutes of each other) to see the time-segment structure. Shows
roll10/breaker context so we can see which clusters the breaker armed for."""
import json
from datetime import datetime, timezone, timedelta
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
GAP_MIN = 90   # losses more than this many minutes apart start a new cluster
DAYS = 3       # look back this many days
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
srcs=[("data/multi_window_engine_live.jsonl","zmkr", lambda o:o.get("filled") is True and o.get("won") is not None),
      ("data/multi_window_engine_15m_live.jsonl","15m", lambda o:o.get("filled") is True and o.get("won") is not None),
      ("data/multi_window_engine_sol_live.jsonl","sol", lambda o:o.get("filled") is True and o.get("won") is not None),
      ("data/early_taker_probe.jsonl","takr", lambda o:o.get("kind")=="entry" and o.get("won") is not None)]
allf=[]
for f,name,keep in srcs:
    try:
        for o in (json.loads(l) for l in open(ROOT+"/"+f,encoding="utf-8") if l.strip()):
            if keep(o):
                w=ws_of(o.get("slug",""))
                if w: allf.append({"eng":name,"ws":w,"coin":o.get("coin"),"side":o.get("side"),"won":bool(o["won"]),
                                   "pnl":float(o.get("pnl",0) or 0),"sh":o.get("sh"),"roll10":o.get("roll10"),"brk":o.get("breaker")})
    except FileNotFoundError: pass
allf.sort(key=lambda x:x["ws"])
maxws=allf[-1]["ws"]; cut=maxws-DAYS*86400
losses=[x for x in allf if not x["won"] and x["ws"]>=cut]
cn=timezone(timedelta(hours=8))
def t(ws,tz=timezone.utc): return datetime.fromtimestamp(ws,tz).strftime("%m-%d %H:%M")
# group into clusters
clusters=[]; cur=[]
for x in losses:
    if cur and (x["ws"]-cur[-1]["ws"])>GAP_MIN*60:
        clusters.append(cur); cur=[]
    cur.append(x)
if cur: clusters.append(cur)
print(f"recent losses (last {DAYS}d): {len(losses)}, total ${sum(x['pnl'] for x in losses):+.2f}, in {len(clusters)} clusters (gap>{GAP_MIN}min)\n")
for i,cl in enumerate(clusters,1):
    span=(cl[-1]["ws"]-cl[0]["ws"])//60
    pnl=sum(x["pnl"] for x in cl)
    big=[x for x in cl if x["sh"] and int(x["sh"])>=20]
    print(f"=== cluster {i}: {t(cl[0]['ws'])}–{t(cl[-1]['ws'])[6:]} UTC ({t(cl[0]['ws'],cn)[6:]} CN) | {len(cl)} losses / {span}min | ${pnl:+.2f}{'  <-- has 20sh+ cell air-pocket' if big else ''} ===")
    for x in cl:
        sh=str(x["sh"]) if x["sh"] else "-"
        print(f"    {t(x['ws'])} {x['eng']:4s} {str(x['coin']):4s} {str(x['side']):5s} {sh:>3s}sh ${x['pnl']:6.2f}  roll10={x.get('roll10')} brk={x.get('brk')}")
print(f"\nREAD: clusters = the bad-regime segments. The breaker arms mid-cluster (roll10 climbs);")
print(f"the FIRST loss of each cluster (esp. a 20sh cell) is the irreducible one it can't pre-empt.")
