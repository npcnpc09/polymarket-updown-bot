"""arb_sim_accum.py — REALISTIC sim of xuanxuan008-style ACCUMULATION two-sided arb.

Not single-shot. We keep a small bid at the best bid on BOTH sides for the whole window
and accumulate toward a target, capturing our FIFO share of real SELL flow:
  per SELL trade (price p, size v) on side X while p<=best_bid_X:
     captured = v * (our_clip / (queue_depth_at_bid + our_clip))   # our FIFO share
     accumulate `captured` shares at price p (until target reached)
End: up_sh,up_cost,dn_sh,dn_cost. Hedged(min) redeems $1/pair (== MERGE). Imbalance=residual
directional. PnL = winner_side_shares*1 - total_cost  (captures adverse-selection tilt).

This is the strategy we CAN actually run (second-scale, not microsecond). ZERO money.
Usage: python arb_sim_accum.py [target_shares]
"""
import json, glob, os, sys
from collections import defaultdict

RECDIR=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"data","recordings")
POST_TTL=240; STOP_TTL=20; CLIP=5.0   # post for whole window; our resting clip size

class Book:
    def __init__(self): self.bids={}; self.asks={}
    def snap(self,bids,asks):
        self.bids={float(b["price"]):float(b["size"]) for b in bids}
        self.asks={float(a["price"]):float(a["size"]) for a in asks}
    def delta(self,ch):
        for x in ch:
            try: p=float(x["price"]); s=float(x["size"]); sd=x.get("side","").upper()
            except: continue
            d=self.asks if sd=="SELL" else self.bids
            if s<=0: d.pop(p,None)
            else: d[p]=s
    def bb(self):
        v=[p for p,s in self.bids.items() if s>0 and p<1]; return max(v) if v else None
    def depth_at(self,P): return sum(s for p,s in self.bids.items() if abs(p-P)<1e-9)

def load():
    recs=sorted(glob.glob(os.path.join(RECDIR,"rec_*.jsonl")))
    f=recs[-1]; wf=f.replace("rec_","windows_")
    wins={}
    for l in open(wf,encoding="utf-8"):
        w=json.loads(l); wins[w["up"]]=w; wins[w["dn"]]=w
    return f, wins

def sim_window(w, evs, target):
    up=w["up"]; dn=w["dn"]; settle=w["settle"]; post_t=settle-POST_TTL; stop_t=settle-STOP_TTL
    books={up:Book(), dn:Book()}
    acc={up:[0.0,0.0], dn:[0.0,0.0]}   # [shares, cost]
    final={up:0.0,dn:0.0}
    for e in evs:
        aid=e["aid"]; et=e["et"]; m=e["m"]; rx=e["rx"]; b=books[aid]
        if et=="book": b.snap(m.get("bids") or [], m.get("asks") or [])
        elif et=="price_change": b.delta(m.get("changes") or m.get("price_changes") or [m])
        elif et=="last_trade_price":
            p=float(m.get("price",0)); final[aid]=p
            if not (post_t<=rx<=stop_t): continue
            if m.get("side","").upper()!="SELL": continue
            bb=b.bb()
            if bb is None or p>bb+1e-9: continue           # only fills bids at/below best bid
            sh,cost=acc[aid]
            if sh>=target-1e-9: continue                    # reached target on this side
            depth=b.depth_at(bb)
            frac=CLIP/(depth+CLIP)                           # our FIFO share of this sell
            cap=min(target-sh, float(m.get("size",0))*frac)
            if cap>0: acc[aid][0]+=cap; acc[aid][1]+=cap*p
    winner = up if final[up]>=final[dn] else dn
    us,uc=acc[up]; ds,dc=acc[dn]
    if us<0.1 and ds<0.1: return {"slug":w["slug"],"outcome":"NO_FILL"}
    win_sh = us if winner==up else ds
    cost=uc+dc; pnl=win_sh*1.0 - cost
    matched=min(us,ds); comb=((uc/us)+(dc/ds)) if (us>0 and ds>0) else None
    return {"slug":w["slug"],"outcome":"ACCUM","up_sh":round(us,1),"dn_sh":round(ds,1),
            "matched":round(matched,1),"imb":round(abs(us-ds),1),"comb":round(comb,3) if comb else None,
            "cost":round(cost,2),"pnl":round(pnl,3)}

def main():
    target=float(sys.argv[1]) if len(sys.argv)>1 else 20.0
    f,wins=load()
    by=defaultdict(list)
    for l in open(f,encoding="utf-8"):
        e=json.loads(l); w=wins.get(e["aid"])
        if w: by[w["slug"]].append(e)
    slugs={w["slug"]:w for w in wins.values()}
    res=[]
    for slug,evs in by.items():
        evs.sort(key=lambda x:x["rx"]); res.append(sim_window(slugs[slug],evs,target))
    print(f"recording: {os.path.basename(f)} | target={target}sh/side | {len(res)} windows\n")
    acc=[r for r in res if r["outcome"]=="ACCUM"]
    for r in acc:
        print(f"  {r['slug'][-10:]} up={r['up_sh']} dn={r['dn_sh']} matched={r['matched']} imb={r['imb']} comb={r['comb']} pnl=${r['pnl']:+.2f}")
    if acc:
        tot=sum(r["pnl"] for r in acc); cost=sum(r["cost"] for r in acc)
        print(f"\n  windows accumulated: {len(acc)}")
        print(f"  avg shares/side: up={sum(r['up_sh'] for r in acc)/len(acc):.1f} dn={sum(r['dn_sh'] for r in acc)/len(acc):.1f}")
        print(f"  avg imbalance: {sum(r['imb'] for r in acc)/len(acc):.1f}sh (0=perfectly hedged)")
        print(f"  median combined price: {sorted(r['comb'] for r in acc if r['comb'])[len(acc)//2]:.3f}")
        print(f"  *** NET PnL: ${tot:+.2f} on ${cost:.0f} deployed = {100*tot/max(cost,1):+.2f}% per cycle ***")
        print("  (REALISTIC accumulation: FIFO share of real sell flow, MERGE hedged, residual tilt)")

if __name__=="__main__": main()
