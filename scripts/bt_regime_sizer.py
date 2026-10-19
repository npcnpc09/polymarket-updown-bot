"""bt_regime_sizer.py — does a CONTINUOUS Bayesian regime-posterior sizer beat the current DISCRETE 5/20/28
tiers on the real cell fills? Run a 2-state HMM forward filter over the COMBINED (taker+zmaker) outcome stream
to get b_t = P(adverse | outcomes before this trade); map b_t -> cell shares via fractional Kelly. Compare
total PnL, shares deployed (matched-risk check), PnL/share, worst-cluster, on full + held-out.

Hyperparameters set A PRIORI (not fit to PnL): W_G/W_B from observed cell win rates, persistence + Kelly frac
from the loss-clustering memory. Sizing is a counterfactual multiplier on REAL outcomes (sizing doesn't change
fill/won), so PnL recompute is clean. CAVEAT: in-sample, ~15 cell losses -> a few air-pockets dominate; held-out
split + matched-shares are the discipline checks."""
import json
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
# combined stream (taker + zmaker), by ws
comb=[]; cells=[]
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl",encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None:
        w=ws_of(o.get("slug",""))
        if w:
            comb.append({"ws":w,"won":bool(o["won"])})
            if o.get("B") and 0.90<=o["B"]<0.96:
                cells.append({"ws":w,"won":bool(o["won"]),"B":float(o["B"])})
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8") if l.strip()):
    if o.get("kind")=="entry" and o.get("won") is not None:
        w=ws_of(o.get("slug",""))
        if w: comb.append({"ws":w,"won":bool(o["won"])})
comb.sort(key=lambda x:x["ws"]); cells.sort(key=lambda x:x["ws"])

# --- 2-state HMM forward filter over combined stream ---
W_G=0.96; W_B=0.80          # win prob in Good / Bad state (a priori from data: cell ~96%, hot-streak ~80%)
P_STAY=0.88                 # regime persistence (a priori; clustering)
def belief_before(ws):
    """P(adverse) using combined outcomes strictly before ws (predicted belief, pre-this-trade)."""
    b=0.15  # prior P(adverse)
    for f in comb:
        if f["ws"]>=ws: break
        # predict (transition)
        b=b*P_STAY+(1-b)*(1-P_STAY)
        # update with this outcome
        LB=(1-W_B) if not f["won"] else W_B
        LG=(1-W_G) if not f["won"] else W_G
        b=b*LB/(b*LB+(1-b)*LG)
    # one more predict step into the current trade
    return b*P_STAY+(1-b)*(1-P_STAY)
def roll10_before(ws):
    prior=[f for f in comb if f["ws"]<ws][-10:]
    return sum(1 for f in prior if not f["won"]), len(prior)

BANK=300.0; KELLY=0.25; CAP=28; FLOOR=5
def kelly_sh(b,B):
    p=(1-b)*W_G+b*W_B
    f=p-(1-p)*B/(1-B)          # full-Kelly fraction for binary @ price B
    sh=KELLY*max(f,0)*BANK/B
    return max(FLOOR,min(CAP,sh))
def discrete_sh(ws):
    r,n=roll10_before(ws)
    if n<10: return 20
    if r>=2: return 5
    if r==0: return 28
    return 20
def pnl(sh,won,B): return sh*(1-B) if won else -sh*B

def run(subset,label):
    flat=disc=cont=0.0; sflat=sdisc=scont=0.0
    for c in subset:
        b=belief_before(c["ws"]); ds=discrete_sh(c["ws"]); ks=kelly_sh(b,c["B"])
        flat+=pnl(20,c["won"],c["B"]); sflat+=20
        disc+=pnl(ds,c["won"],c["B"]); sdisc+=ds
        cont+=pnl(ks,c["won"],c["B"]); scont+=ks
    print(f"  {label} (n={len(subset)} cell fills):")
    print(f"    FLAT-20         PnL=${flat:+8.2f}  shares={sflat:7.0f}  $/sh={flat/sflat:+.4f}")
    print(f"    DISCRETE 5/20/28 PnL=${disc:+8.2f}  shares={sdisc:7.0f}  $/sh={disc/sdisc:+.4f}")
    print(f"    CONTINUOUS Kelly PnL=${cont:+8.2f}  shares={scont:7.0f}  $/sh={cont/scont:+.4f}")
print(f"combined stream {len(comb)} fills | cell fills {len(cells)}")
print(f"\n=== FULL period ===")
run(cells,"ALL")
cut=cells[int(len(cells)*0.6)]["ws"]
print(f"\n=== TRAIN (first 60%) / HELD-OUT (last 40%) ===")
run([c for c in cells if c["ws"]<cut],"TRAIN")
run([c for c in cells if c["ws"]>=cut],"HELD-OUT")
# show belief at the air-pockets
print(f"\n=== regime belief b_t at the 20sh+ cell losses (air-pockets) — did the sizer see them coming? ===")
for c in cells:
    if not c["won"]:
        b=belief_before(c["ws"]); r,n=roll10_before(c["ws"])
        from datetime import datetime,timezone
        t=datetime.fromtimestamp(c["ws"],timezone.utc).strftime("%m-%d %H:%M")
        print(f"    {t} B={c['B']} b_adverse={b:.2f} roll10={r}/{n} -> contKelly={kelly_sh(b,c['B']):.0f}sh vs discrete={discrete_sh(c['ws'])}sh")
print("\nREAD: continuous WINS if higher PnL at <= shares (matched/less risk) AND held-out holds. The air-pocket")
print("table shows whether either sizer had b/roll10 elevated BEFORE the loss (caught it) or low (ate it full).")
