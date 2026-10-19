"""bt_panel_theta2.py — fair test using the EXACT breaker metric (rolling-10 fills, >=2 losses = armed). Does
the denser PANEL stream predict cell losses better than OWN / COMBINED? For each cell fill, compute rolling-10
(strictly prior) under each stream; cell-loss% when armed (>=2) vs not. Reproduces the breaker for COMB, tests
if PANEL improves. Also reports the TIME span of each stream's last-10 (density => shorter span => more recent
theta)."""
import json, statistics as st
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
                if w: out.append({"ws":w,"won":bool(o["won"]),"B":o.get("B")})
    except FileNotFoundError: pass
    return out
zm=load("data/multi_window_engine_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None)
tk=load("data/early_taker_probe.jsonl",lambda o:o.get("kind")=="entry" and o.get("won") is not None)
sol=load("data/multi_window_engine_sol_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None)
m15=load("data/multi_window_engine_15m_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None)
own=sorted(zm,key=lambda x:x["ws"]); comb=sorted(zm+tk,key=lambda x:x["ws"]); panel=sorted(zm+tk+sol+m15,key=lambda x:x["ws"])
cells=sorted([f for f in zm if f["B"] and 0.90<=f["B"]<0.96],key=lambda x:x["ws"])
def roll(stream,ws,N=10):
    s=[f for f in stream if f["ws"]<ws][-N:]
    if len(s)<N: return None,None
    losses=sum(1 for f in s if not f["won"]); span=(ws-s[0]["ws"])/60.0
    return losses,span
def analyze(stream,name,K=2):
    armed=[]; calm=[]; spans=[]
    for c in cells:
        l,span=roll(stream,c["ws"])
        if l is None: continue
        spans.append(span)
        (armed if l>=K else calm).append(c["won"])
    def lr(s): return sum(1 for w in s if not w)/len(s)*100 if s else 0
    lift=lr(armed)-lr(calm)
    print(f"  {name}: armed(roll10>={K}) n={len(armed):3d} cell-loss%={lr(armed):4.1f} | calm n={len(calm):3d} cell-loss%={lr(calm):4.1f} | LIFT={lift:+5.1f}pp | last10 spans ~{st.median(spans):.0f}min")
print(f"streams: own={len(own)} comb={len(comb)} panel={len(panel)} | cell events={len(cells)}\n")
print("=== cell-loss% when armed vs calm (breaker metric, rolling-10 >=2 losses) ===")
analyze(own,"(1) OWN  zmaker     ")
analyze(comb,"(2) COMB taker+zmkr ")
analyze(panel,"(3) PANEL all       ")
print("\nREAD: PANEL beats COMB only if its LIFT is clearly higher (denser=more recent theta=earlier detection).")
print("If panel lift ~= comb lift -> cross-section adds nothing beyond taker+zmaker (shared signal saturated).")
