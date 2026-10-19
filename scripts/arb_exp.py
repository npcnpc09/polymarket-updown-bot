"""arb_exp.py — THE comb-left-shift experiment.

On the SAME recorder windows, maker-only accumulate both sides (FIFO capture of real SELL
flow at our bid, NEVER lift asks). Then handle the residual imbalance 3 ways and compare:
  A COMPLETE: buy the missing leg at the ASK (chase)         -> inflates comb
  B SCRATCH : sell the excess leg at its BID (patient unwind)-> eat only spread/move
  C HOLD    : keep the excess directional (gamble)
Report per policy: net PnL/cycle, and matched-pair comb stats. Also test whether realized
comb is PREDICTABLE from an observable at post time (initial bid_sum). ZERO money.

Usage: python arb_exp.py [target] [post_ttl] [stop_ttl]
"""
import json, glob, os, sys, statistics
from collections import defaultdict

RECDIR=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"data","recordings")

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
    def depth_at(self,P): return sum(s for p,s in self.bids.items() if abs(p-P)<1e-9)
    def walk_ask(self,n):
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

def sim(w, evs, target, post_ttl, stop_ttl, clip=5.0):
    up=w["up"]; dn=w["dn"]; settle=w["settle"]; post_t=settle-post_ttl; stop_t=settle-stop_ttl
    books={up:Book(), dn:Book()}; acc={up:[0.0,0.0], dn:[0.0,0.0]}; final={up:0.0,dn:0.0}
    init_bidsum=None; snap_stop=None
    for e in evs:
        aid=e["aid"]; et=e["et"]; m=e["m"]; rx=e["rx"]; b=books[aid]
        if et=="book": b.snap(m.get("bids") or [], m.get("asks") or [])
        elif et=="price_change": b.delta(m.get("changes") or m.get("price_changes") or [m])
        elif et=="last_trade_price":
            p=float(m.get("price",0)); final[aid]=p
            if not (post_t<=rx<=stop_t) or m.get("side","").upper()!="SELL": continue
            bb=b.bb()
            if bb is None or p>bb+1e-9: continue
            sh,cost=acc[aid]
            if sh>=target-1e-9: continue
            frac=clip/(b.depth_at(bb)+clip)
            cap=min(target-sh, float(m.get("size",0))*frac)
            if cap>0: acc[aid][0]+=cap; acc[aid][1]+=cap*p
        # capture observable at post, and book snapshot near stop
        if init_bidsum is None and books[up].bb() is not None and books[dn].bb() is not None:
            init_bidsum=books[up].bb()+books[dn].bb()
    us,uc=acc[up]; ds,dc=acc[dn]
    if us<0.5 or ds<0.5: return None
    pu=uc/us; pd=dc/ds; comb=pu+pd
    matched=min(us,ds)
    winner=up if final[up]>=final[dn] else dn
    bbu=books[up].bb() or final[up] or 0.5; bbd=books[dn].bb() or final[dn] or 0.5
    # base: matched pairs settle/merge at $1 each
    base = matched*1.0 - matched*pu - matched*pd if False else matched*(1.0-comb)
    # residual handling on the heavy side
    heavy, hsh, hp, hbb = (up,us,pu,bbu) if us>=ds else (dn,ds,pd,bbd)
    light = dn if heavy==up else up
    excess = abs(us-ds)
    # A COMPLETE: buy `excess` of light at its ask
    avg_ask,got = books[light].walk_ask(excess)
    if avg_ask and got>0:
        # the completed pairs: pay hp (heavy) + avg_ask (light), settle $1
        comp_pnl = base + got*(1.0 - hp - avg_ask) + (excess-got)*(0 if winner==light else 0)  # unfilled excess stays heavy -> handle as hold
        # any unfillable remainder: hold heavy
        rem=excess-got
        comp_pnl += rem*((1.0 if winner==heavy else 0.0) - hp)
    else:
        comp_pnl = base + excess*((1.0 if winner==heavy else 0.0) - hp)  # couldn't complete -> hold
    # B SCRATCH: sell `excess` of heavy at its bid
    scratch_pnl = base + excess*(hbb - hp)
    # C HOLD: keep excess directional
    hold_pnl = base + excess*((1.0 if winner==heavy else 0.0) - hp)
    deploy = uc+dc
    return {"slug":w["slug"],"comb":comb,"matched":matched,"imb":excess,"deploy":deploy,
            "A":comp_pnl,"B":scratch_pnl,"C":hold_pnl,"init_bidsum":init_bidsum}

def main():
    target=float(sys.argv[1]) if len(sys.argv)>1 else 20.0
    post_ttl=float(sys.argv[2]) if len(sys.argv)>2 else 240.0
    stop_ttl=float(sys.argv[3]) if len(sys.argv)>3 else 20.0
    f,wins=load()
    by=defaultdict(list)
    for l in open(f,encoding="utf-8"):
        e=json.loads(l); w=wins.get(e["aid"])
        if w: by[w["slug"]].append(e)
    slugs={w["slug"]:w for w in wins.values()}
    res=[r for s,ev in by.items() for r in [sim(slugs[s],sorted(ev,key=lambda x:x["rx"]),target,post_ttl,stop_ttl)] if r]
    if not res: print("no windows"); return
    print(f"target={target} post_ttl={post_ttl} stop_ttl={stop_ttl} | {len(res)} windows\n")
    combs=sorted(r["comb"] for r in res)
    capped=sum(1 for r in res if min(r['matched']+r['imb'], r['matched'])>=target-0.5)
    print(f"  realized matched-comb: median={statistics.median(combs):.4f}  %comb<1={100*sum(1 for x in combs if x<1)//len(combs)}%  min={combs[0]:.3f} max={combs[-1]:.3f}")
    print(f"  avg imbalance(excess): {sum(r['imb'] for r in res)/len(res):.1f}sh of {target} | windows hitting target cap: {capped}/{len(res)}\n")
    dep=sum(r["deploy"] for r in res)
    for pol,name in (("A","COMPLETE@ask (chase)"),("B","SCRATCH@bid (patient)"),("C","HOLD (gamble)")):
        tot=sum(r[pol] for r in res); wn=sum(1 for r in res if r[pol]>0)
        print(f"  {name:<24} NET ${tot:+8.2f}  ROI {100*tot/max(dep,1):+.2f}%/cyc  win {100*wn//len(res)}%  avg ${tot/len(res):+.3f}")
    # predictability: does init_bidsum predict comb<1?  (sort & split into thirds, robust)
    pv=sorted([(r["init_bidsum"],r["comb"]) for r in res if r["init_bidsum"] is not None])
    print(f"\n  PREDICTABILITY (does post-time bid_sum forecast realized comb?):  usable={len(pv)}/{len(res)}")
    if len(pv)>=6:
        k=max(1,len(pv)//3)
        lo=[c for b,c in pv[:k]]; hi=[c for b,c in pv[-k:]]
        print(f"    LOW  init bid_sum (bottom {k}, bidsum {pv[0][0]:.3f}-{pv[k-1][0]:.3f}): median comb={statistics.median(lo):.4f} %win={100*sum(1 for c in lo if c<1)//len(lo)}%")
        print(f"    HIGH init bid_sum (top {k}, bidsum {pv[-k][0]:.3f}-{pv[-1][0]:.3f}): median comb={statistics.median(hi):.4f} %win={100*sum(1 for c in hi if c<1)//len(hi)}%")
        import statistics as st
        try:
            bs=[b for b,c in pv]; cs=[c for b,c in pv]
            corr=st.correlation(bs,cs) if hasattr(st,'correlation') else None
            print(f"    corr(init_bidsum, realized_comb) = {corr:+.3f}  (>0 means high bidsum -> high comb -> avoidable)")
        except Exception as e: print(f"    corr n/a: {e}")
        print(f"    -> if LOW bidsum reliably gives comb<1, post-time bid_sum is a usable ex-ante SKIP filter")

if __name__=="__main__": main()
