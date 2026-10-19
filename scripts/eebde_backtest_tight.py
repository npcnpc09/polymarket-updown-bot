"""eebde_backtest.py â€” Backtest strategies against eebde's REAL fill prices (7d, btc/eth).

Price oracle: from his actual fills. At each of his trade times, price(Up) = his fill
if he bought Up, else 1 - fill (complementary). Gives a realistic Up/Down price path
per window. We then run DIFFERENT strategies over the SAME price path and compare ROI,
so we test OUR decision rule against the real prices he traded at.

Strategies:
  REPLAY      - buy exactly what he bought (= his actual ROI, baseline)
  MOM_RAMP    - our eebde-replication: at each tick, buy the BTC-leading side, size
                ramped by |move| (small early/balanced, big when move clear)
  SINGLE_EARLY- one buy on the leading side early in the window (our old probe)
  SINGLE_LATE - one buy on the leading side late
  ORACLE_WIN  - buy the eventual winner every tick (cheat upper bound)

Capital-independent (ROI). Reports ROI + alignment of each strategy's net tilt vs his.
"""
import json, bisect, statistics
from collections import defaultdict

DATA = r"C:\Users\Administrator\Desktop\polymarket_arb_deploy_full\data"

def loadk(fn):
    t=[]; c=[]
    for l in open(DATA+"\\"+fn, encoding="utf-8"):
        k=json.loads(l); t.append(k["t"]); c.append(k["c"])
    return t,c
K={"btc":loadk("btc_1m_klines.jsonl"),"eth":loadk("eth_1m_klines.jsonl")}
def px(coin,ts):
    t,c=K[coin]; i=bisect.bisect_right(t,ts)-1
    return c[i] if 0<=i<len(c) else None

# build per-window events from his fills
mkt=defaultdict(list); meta={}
for line in open(DATA+r"\eebde_history_7d.jsonl", encoding="utf-8"):
    try: e=json.loads(line)
    except: continue
    if e.get("type")!="TRADE" or e.get("side")!="BUY": continue
    s=e.get("slug",""); coin=s.split("-updown-")[0] if "-updown-" in s else None
    if coin not in ("btc","eth"): continue
    try: st=int(s.rsplit("-",1)[1])
    except: continue
    du=300 if "-5m-" in s else (900 if "-15m-" in s else None)
    if not du: continue
    cid=e["conditionId"]
    p=float(e["price"]); oc=e.get("outcome")
    mkt[cid].append((e["timestamp"], oc, float(e["usdcSize"]), p))
    meta[cid]=(coin,st,du)

def settle_winner(coin,st,du):
    op=px(coin,st); se=px(coin,st+du)
    if op is None or se is None: return None,None
    return ("Up" if se>=op else "Down"), op

class PriceOracle:
    """Per-side REAL ask price from his actual fills (no complementary guessing)."""
    def __init__(self, evs):
        self.s={"Up":[],"Down":[]}
        for ts,oc,usd,p in sorted(evs):
            if oc in self.s: self.s[oc].append((ts,p))
    def price(self, side, ts):
        arr=self.s.get(side) or []
        if not arr: return None
        # nearest real fill on that side by time
        best=min(arr,key=lambda x:abs(x[0]-ts))
        if abs(best[0]-ts)>20: return None   # no real ask within 3min -> can't price
        return best[1]

class Book:
    def __init__(self, oracle): self.cost=0.0; self.win_sh=0.0; self.up_sh=0.0; self.dn_sh=0.0; self.o=oracle; self.skipped=0
    def buy(self, outcome, dollars, ts, winner):
        p=self.o.price(outcome, ts)
        if p is None: self.skipped+=1; return
        p=max(0.01,min(0.99,p)); sh=dollars/p; self.cost+=dollars
        if outcome=="Up": self.up_sh+=sh
        else: self.dn_sh+=sh
        if outcome==winner: self.win_sh+=sh
    def roi(self):
        if self.cost<=0: return None
        return (self.win_sh*1.0 - self.cost)/self.cost
    def tilt(self):
        return "Up" if self.up_sh>=self.dn_sh else "Down"

agg=defaultdict(lambda:{"cost":0.0,"pnl":0.0,"align":0,"n":0})
for cid,evs in mkt.items():
    coin,st,du=meta[cid]
    winner,op=settle_winner(coin,st,du)
    if winner is None or op is None or len(evs)<2: continue
    evs.sort()
    oracle=PriceOracle(evs)
    his_tilt_up=sum(s for _,o,s,_ in evs if o=="Up"); his_tilt_dn=sum(s for _,o,s,_ in evs if o=="Down")
    his_tilt="Up" if his_tilt_up>=his_tilt_dn else "Down"
    ticks=[]
    for ts,oc,usd,p in evs:
        bp=px(coin,ts); mv=(bp/op-1)*1e4 if bp else 0.0
        lead="Up" if mv>=0 else "Down"; ttl=st+du-ts
        ticks.append((ts,oc,usd,mv,lead,ttl))

    strat={}
    # REPLAY
    b=Book(oracle)
    for ts,oc,usd,mv,lead,ttl in ticks: b.buy(oc,usd,ts,winner)
    strat["REPLAY"]=b
    # MOM_RAMP: buy leading side, size ramps with |mv|
    b=Book(oracle)
    for ts,oc,usd,mv,lead,ttl in ticks: b.buy(lead,min(40.0,5.0*(1+abs(mv)/4.0)),ts,winner)
    strat["MOM_RAMP"]=b
    # SINGLE_EARLY
    b=Book(oracle); done=False
    for ts,oc,usd,mv,lead,ttl in ticks:
        if not done and ttl<=du*0.9 and abs(mv)>=2: b.buy(lead,100.0,ts,winner); done=True
    if b.cost>0: strat["SINGLE_EARLY"]=b
    # SINGLE_LATE
    b=Book(oracle); cand=[t for t in ticks if t[5]>=20 and abs(t[3])>=2]
    if cand:
        ts,oc,usd,mv,lead,ttl=cand[-1]; b.buy(lead,100.0,ts,winner)
        if b.cost>0: strat["SINGLE_LATE"]=b
    # ORACLE_WIN
    b=Book(oracle)
    for ts,oc,usd,mv,lead,ttl in ticks: b.buy(winner,5.0,ts,winner)
    strat["ORACLE_WIN"]=b

    for name,bk in strat.items():
        r=bk.roi()
        if r is None: continue
        a=agg[name]; a["cost"]+=bk.cost; a["pnl"]+=bk.win_sh*1.0-bk.cost; a["n"]+=1
        if bk.tilt()==his_tilt: a["align"]+=1

print(f"backtest over {len(mkt)} btc/eth markets (his real fill prices as oracle)\n")
print(f"{'strategy':<13}{'n':>6}{'ROI':>9}{'align_vs_his':>14}")
for name in ["REPLAY","MOM_RAMP","SINGLE_EARLY","SINGLE_LATE","ORACLE_WIN"]:
    a=agg.get(name)
    if not a or a["cost"]<=0: continue
    roi=100*a["pnl"]/a["cost"]; al=100*a["align"]//max(a["n"],1)
    print(f"{name:<13}{a['n']:>6}{roi:>+8.2f}%{al:>12}%")
print("\nnote: REPLAY=his actual; ORACLE_WIN=cheat upper bound; MOM_RAMP=our eebde-replication")
