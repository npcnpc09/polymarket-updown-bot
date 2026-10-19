"""bt_panel_theta.py — TEST the cross-sectional latent-theta theory: does a DENSER panel of outcomes estimate
the shared adverse state theta_t better than our sparse single/combined stream? For each CELL fill (zmaker
btc/eth 0.90-0.95), compute the prior-30min loss rate under 3 streams of increasing density:
  (1) own    = zmaker btc/eth only
  (2) comb   = taker + zmaker btc/eth (current breaker)
  (3) panel  = taker + zmaker + sol + 15m, ALL coins/engines (the cross-section)
Then bucket cell outcomes by each stream's prior-loss-rate. Theory holds if the PANEL's prior-loss-rate
separates cell wins/losses MORE sharply (higher loss-rate lift in its high bucket) = it sees theta_t with less
delay. Time-window (30min) not fill-count, so denser streams aren't unfairly favored — they just have more
samples IN the window = lower-variance theta estimate."""
import json
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
def load(f,keep):
    out=[]
    try:
        for o in (json.loads(l) for l in open(ROOT+"/"+f,encoding="utf-8") if l.strip()):
            if keep(o):
                w=ws_of(o.get("slug",""))
                if w: out.append({"ws":w,"won":bool(o["won"]),"coin":o.get("coin"),"B":o.get("B"),"sh":o.get("sh")})
    except FileNotFoundError: pass
    return out
zm=load("data/multi_window_engine_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None)
tk=load("data/early_taker_probe.jsonl",lambda o:o.get("kind")=="entry" and o.get("won") is not None)
sol=load("data/multi_window_engine_sol_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None)
m15=load("data/multi_window_engine_15m_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None)
own=sorted(zm,key=lambda x:x["ws"])
comb=sorted(zm+tk,key=lambda x:x["ws"])
panel=sorted(zm+tk+sol+m15,key=lambda x:x["ws"])
cells=sorted([f for f in zm if f["B"] and 0.90<=f["B"]<0.96],key=lambda x:x["ws"])
T=1800  # 30-min prior window
def prior_lossrate(stream,ws):
    s=[f for f in stream if ws-T<=f["ws"]<ws]
    if len(s)<3: return None
    return sum(1 for f in s if not f["won"])/len(s), len(s)
def analyze(stream,name):
    buckets={"low":[],"med":[],"high":[]}
    for c in cells:
        pr=prior_lossrate(stream,c["ws"])
        if pr is None: continue
        lr,n=pr
        b="low" if lr<0.10 else ("high" if lr>=0.25 else "med")
        buckets[b].append(c["won"])
    print(f"  {name} (prior-30min loss rate -> this cell's loss rate):")
    for b in ("low","med","high"):
        s=buckets[b]
        if s: print(f"    prior {b:4s} (lr {'<10%' if b=='low' else ('>=25%' if b=='high' else '10-25%')}): n={len(s):3d} cell-loss%={sum(1 for w in s if not w)/len(s)*100:5.1f}")
        else: print(f"    prior {b:4s}: n=0")
print(f"streams: own={len(own)} comb={len(comb)} panel={len(panel)} | cell events={len(cells)}\n")
print("=== does prior loss rate predict the cell loss? (sharper separation = better theta estimator) ===")
analyze(own,"(1) OWN  zmaker-only ")
analyze(comb,"(2) COMB taker+zmaker")
analyze(panel,"(3) PANEL all coins+engines")
print("\nREAD: theory holds if PANEL's high-bucket cell-loss% is clearly higher than COMB's/OWN's (panel detects")
print("the adverse theta with more samples = less delay/variance). If all similar -> extra coins add no info")
print("beyond the combined stream (the shared-factor signal is already saturated by taker+zmaker).")
