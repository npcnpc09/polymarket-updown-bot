"""Resolve the paper orders logged by strategy_paper_6e1d.py --live and compute
REAL-FILL paper PnL (bought at the live CLOB ask, held to resolution). This is
the decisive proof that the reconstructed strategy is profitable at prices *I*
can actually get, not at 6e1d's entry prices. Re-runnable as more markets settle.
"""
import httpx, json, os
from collections import defaultdict

LOG="data/strategy_paper_6e1d.jsonl"
sess=httpx.Client(timeout=25, headers={"User-Agent":"Mozilla/5.0"})

def load(ev):
    rows=[]
    if not os.path.exists(LOG): return rows
    for ln in open(LOG):
        try:
            o=json.loads(ln)
            if o.get("ev")==ev: rows.append(o)
        except: pass
    return rows

# unique resolution lookup
def resolve(cids):
    res={}
    cl=sorted(set(cids))
    for i in range(0,len(cl),20):
        batch=cl[i:i+20]
        # query both closed=true AND no-filter; expired-but-UMA-pending markets
        # have decisive outcomePrices before the `closed` flag flips -> accept either.
        merged={}
        for params in ([("closed","true")], []):
            try:
                d=sess.get("https://gamma-api.polymarket.com/markets",
                   params=params+[("condition_ids",c) for c in batch]).json()
            except Exception: d=[]
            for m in (d if isinstance(d,list) else []):
                merged[m.get("conditionId")]=m
        for cid,m in merged.items():
            try: op=[float(x) for x in json.loads(m.get("outcomePrices","[]"))]
            except: op=None
            try: outs=json.loads(m.get("outcomes","[]"))
            except: outs=[]
            res[cid]=dict(op=op,outs=outs,closed=m.get("closed"),q=m.get("question",""))
    return res

def side_idx(side, outs):
    for i,o in enumerate(outs):
        if o.lower()==side.lower(): return i
    return 0 if side.lower()=="yes" else 1

def settle(rows, label):
    res=resolve([r["cid"] for r in rows])
    n=w=pend=0; pnl=0.0; staked=0.0; rows_done=[]
    for r in rows:
        m=res.get(r["cid"])
        if not m or not m.get("op") or max(m["op"])<0.99:
            pend+=1; continue
        idx=side_idx(r["side"], m["outs"] or ["Yes","No"])
        win = m["op"][idx]>0.99
        ask=r.get("ask"); size=r.get("size",20.0)
        if not ask: continue
        tp = size*(1.0/ask-1.0) if win else -size
        n+=1; w+=1 if win else 0; pnl+=tp; staked+=size
        rows_done.append((win,r,tp,m["q"]))
    print(f"\n=== {label} ===")
    print(f"  resolved: {n}  pending: {pend}")
    if n:
        print(f"  WR: {w/n*100:.1f}%   PnL: ${pnl:+.2f}   staked: ${staked:.0f}   "
              f"ROI: {pnl/staked*100:+.1f}%   EV/trade: {pnl/n*100:+.1f}%")
        print("  detail:")
        for win,r,tp,q in sorted(rows_done,key=lambda x:x[2]):
            print(f"    {'WIN ' if win else 'LOSS'} {r['side']:4} ask={r['ask']:<5} "
                  f"fair={r.get('fair')} edge=+{r.get('edge')}  ${tp:+6.2f}  {q[:42]}")
    return pnl,n,pend

print("="*70)
print("PAPER PnL — my strategy's orders at REAL live-ask fills, held to resolve")
print("="*70)
my=load("MY_ORDER")
print(f"total MY_ORDER logged: {len(my)}")
settle(my, "MY INDEPENDENT PAPER ORDERS")

# Also: his AGREE trades — did the trades my model endorsed actually win?
his=[h for h in load("HIS_TRADE") if h.get("verdict")=="AGREE" and h.get("price")]
print(f"\ntotal HIS_TRADE verdict=AGREE logged: {len(his)}")
# reuse settle structure: treat his price as ask
for h in his: h["ask"]=h["price"]; h["size"]=h.get("usd") or 20.0
settle(his, "HIS TRADES MY MODEL ENDORSED (AGREE) — at his price")
