"""arb_sim.py — REALISTIC offline simulator for two-sided maker arb (replays recording).

Models the pitfalls we hit/anticipate:
  - FIFO QUEUE: our 5sh bid sits BEHIND the existing size at the best bid; fills only when
    cumulative SELL volume at price<=our_bid (after post) exceeds queue_ahead + 5.
  - can't jump queue: we post AT the bid (margin=spread); posting higher kills margin.
  - HALF-leg completion at the ASK *at completion time* (grace end) -> ADVERSE MOVE captured;
    walks the recorded ask book -> PARTIAL FILL if thin -> residual under-hedge.
  - PnL = winning_side_shares - total_cost  (captures residual directional tilt exactly).
  - skip if our bid would CROSS at post (can't be maker).

Winner from final recorded trade prices. ZERO money. Usage: python arb_sim.py
"""
import json, glob, os, sys
from collections import defaultdict

RECDIR=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"data","recordings")
SHARES=5.0; POST_TTL=230; COMPLETE_TTL=40   # post@ttl230, let bids fill ~190s, complete laggard@ttl40

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
    def ba(self):
        v=[p for p,s in self.asks.items() if s>0 and p>0]; return min(v) if v else None
    def depth_at_bid(self,P): return sum(s for p,s in self.bids.items() if abs(p-P)<1e-9)
    def walk_ask(self,n):
        """buy n shares walking asks. returns (avg_price, shares_got)."""
        rem=n; cost=0.0; got=0.0
        for p,s in sorted(self.asks.items()):
            if p>=1.0 or s<=0: continue
            take=min(rem,s); cost+=take*p; got+=take; rem-=take
            if rem<=1e-9: break
        return (cost/got if got>0 else None), got

def load():
    recs=sorted(glob.glob(os.path.join(RECDIR,"rec_*.jsonl")))
    f=recs[-1]; wf=f.replace("rec_","windows_")
    wins={}
    for l in open(wf,encoding="utf-8"):
        w=json.loads(l); wins[w["up"]]=w; wins[w["dn"]]=w
    return f, wins

def sim_window(w, evs):
    up=w["up"]; dn=w["dn"]; settle=w["settle"]; post_t=settle-POST_TTL; grace_end=settle-COMPLETE_TTL
    books={up:Book(), dn:Book()}
    legs={up:None, dn:None}          # {"bid","queue","sellvol","filled","sh","cost"}
    posted=False; completed=False; final={up:0.0,dn:0.0}
    res={"slug":w["slug"]}
    for e in evs:
        aid=e["aid"]; et=e["et"]; m=e["m"]; rx=e["rx"]; b=books[aid]
        if et=="book": b.snap(m.get("bids") or [], m.get("asks") or [])
        elif et=="price_change": b.delta(m.get("changes") or m.get("price_changes") or [m])
        elif et=="last_trade_price":
            p=float(m.get("price",0)); final[aid]=p
            if posted and legs[aid] and not legs[aid]["filled"] and m.get("side","").upper()=="SELL" and p<=legs[aid]["bid"]+1e-9:
                legs[aid]["sellvol"]+=float(m.get("size",0))
                if legs[aid]["sellvol"]>=legs[aid]["queue"]+SHARES-1e-6:
                    legs[aid]["filled"]=True; legs[aid]["sh"]=SHARES; legs[aid]["cost"]=SHARES*legs[aid]["bid"]
        # POST at post_t (as maker at the bid; skip if would cross)
        if not posted and rx>=post_t:
            ok=True
            for tok in (up,dn):
                bb=books[tok].bb(); ba=books[tok].ba()
                if bb is None or ba is None or bb>=ba: ok=False; break
                legs[tok]={"bid":bb,"queue":books[tok].depth_at_bid(bb),"sellvol":0.0,"filled":False,"sh":0.0,"cost":0.0}
            posted=True if ok else False
            if not ok: legs={up:None,dn:None}; res["outcome"]="NO_POST_CROSS";
        # COMPLETE at grace_end (use book NOW = adverse move + partial)
        if posted and not completed and rx>=grace_end:
            completed=True
            fu=legs[up]["filled"]; fd=legs[dn]["filled"]
            if fu and fd: res["outcome"]="BOTH"
            elif fu or fd:
                miss = dn if fu else up
                avg,got=books[miss].walk_ask(SHARES)
                if avg and got>0:
                    legs[miss]["sh"]=got; legs[miss]["cost"]=avg*got
                res["outcome"]="HALF_COMPLETED"; res["comp_got"]=round(got,1) if avg else 0
            else: res["outcome"]="NONE"
    if not posted: res.setdefault("outcome","NO_DATA"); return res
    if res.get("outcome") in ("NO_POST_CROSS","NO_DATA"): return res
    if not completed:  # window ended before grace? treat by current fills
        res.setdefault("outcome","INCOMPLETE")
    winner = up if final[up]>=final[dn] else dn
    us=legs[up]["sh"] if legs[up] else 0; uc=legs[up]["cost"] if legs[up] else 0
    ds=legs[dn]["sh"] if legs[dn] else 0; dc=legs[dn]["cost"] if legs[dn] else 0
    win_sh = (us if winner==up else ds)
    cost=uc+dc
    res["pnl"]=round(win_sh*1.0 - cost,3) if cost>0 else None
    res["up_sh"]=round(us,1); res["dn_sh"]=round(ds,1); res["imb"]=round(abs(us-ds),1)
    res["bid_sum"]=round((legs[up]["bid"]+legs[dn]["bid"]),3) if (legs[up] and legs[dn]) else None
    return res

def main():
    f,wins=load()
    by=defaultdict(list)
    for l in open(f,encoding="utf-8"):
        e=json.loads(l); w=wins.get(e["aid"])
        if w: by[w["slug"]].append(e)
    slugs={w["slug"]:w for w in wins.values()}
    res=[]
    for slug,evs in by.items():
        evs.sort(key=lambda x:x["rx"])
        res.append(sim_window(slugs[slug], evs))
    from collections import Counter
    print(f"recording: {os.path.basename(f)} | {len(res)} windows")
    print("outcomes:", dict(Counter(r["outcome"] for r in res)))
    pnls=[r["pnl"] for r in res if r.get("pnl") is not None]
    both=[r for r in res if r["outcome"]=="BOTH"]; half=[r for r in res if r["outcome"]=="HALF_COMPLETED"]
    print("\n  detail:")
    for r in res:
        if r.get("pnl") is not None:
            print(f"   {r['slug'][-10:]} {r['outcome']:<15} bid_sum={r.get('bid_sum')} up={r.get('up_sh')} dn={r.get('dn_sh')} imb={r.get('imb')} pnl=${r['pnl']:+.2f}")
    if pnls:
        bf=100*len(both)//max(len(both)+len(half),1)
        print(f"\n  both-fill rate: {bf}% (BOTH={len(both)} HALF={len(half)})")
        print(f"  *** NET sim PnL: ${sum(pnls):+.2f} over {len(pnls)} cycles = {100*sum(pnls)/(SHARES*len(pnls)):+.2f}%/cycle ***")
        print("  (REALISTIC: real queue/FIFO, completion at adverse ask, partial fills, residual tilt)")

if __name__=="__main__": main()
