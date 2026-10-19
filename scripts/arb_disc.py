"""arb_disc.py — PRICE-DISCIPLINED accumulation (xuanxuan008's real edge).

Only take a fill on side X at price p IF p + (other side's best bid) <= THRESH.
=> every share kept keeps instant combined < THRESH -> only buy when it's genuinely arb.
Cost: accumulate slower, may stay imbalanced. ZERO money.
Usage: python arb_disc.py [target] [thresh]
"""
import json, glob, os, sys
from collections import defaultdict

RECDIR=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"data","recordings")
POST_TTL=240; STOP_TTL=20; CLIP=5.0

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

def sim_window(w, evs, target, thresh):
    up=w["up"]; dn=w["dn"]; settle=w["settle"]; post_t=settle-POST_TTL; stop_t=settle-STOP_TTL
    books={up:Book(), dn:Book()}; acc={up:[0.0,0.0], dn:[0.0,0.0]}; final={up:0.0,dn:0.0}
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
            other=dn if aid==up else up; ob=books[other].bb()
            if ob is None or (p+ob)>thresh: continue          # PRICE DISCIPLINE
            frac=CLIP/(b.depth_at(bb)+CLIP)
            cap=min(target-sh, float(m.get("size",0))*frac)
            if cap>0: acc[aid][0]+=cap; acc[aid][1]+=cap*p
    winner=up if final[up]>=final[dn] else dn
    us,uc=acc[up]; ds,dc=acc[dn]
    if us<0.1 and ds<0.1: return {"outcome":"NO_FILL"}
    win_sh=us if winner==up else ds; cost=uc+dc; pnl=win_sh*1.0-cost
    comb=((uc/us)+(dc/ds)) if (us>0 and ds>0) else None
    return {"slug":w["slug"],"outcome":"ACCUM","up":round(us,1),"dn":round(ds,1),
            "imb":round(abs(us-ds),1),"comb":round(comb,3) if comb else None,"cost":round(cost,2),"pnl":round(pnl,3)}

def main():
    target=float(sys.argv[1]) if len(sys.argv)>1 else 20.0
    thresh=float(sys.argv[2]) if len(sys.argv)>2 else 0.99
    f,wins=load()
    by=defaultdict(list)
    for l in open(f,encoding="utf-8"):
        e=json.loads(l); w=wins.get(e["aid"])
        if w: by[w["slug"]].append(e)
    slugs={w["slug"]:w for w in wins.values()}
    res=[sim_window(slugs[s],sorted(ev,key=lambda x:x["rx"]),target,thresh) for s,ev in by.items()]
    acc=[r for r in res if r["outcome"]=="ACCUM"]
    print(f"target={target} thresh={thresh} | {len(acc)} windows")
    for r in acc:
        print(f"  {r['slug'][-10:]} up={r['up']} dn={r['dn']} imb={r['imb']} comb={r['comb']} pnl=${r['pnl']:+.2f}")
    if acc:
        tot=sum(r["pnl"] for r in acc); cost=sum(r["cost"] for r in acc)
        combs=sorted(r["comb"] for r in acc if r["comb"])
        print(f"\n  avg imbalance={sum(r['imb'] for r in acc)/len(acc):.1f}sh | avg sh/side={sum(r['up']+r['dn'] for r in acc)/(2*len(acc)):.1f}(tgt{target}) | median comb={combs[len(combs)//2] if combs else 0:.3f}")
        print(f"  *** NET ${tot:+.2f} on ${cost:.0f} = {100*tot/max(cost,1):+.2f}%/cycle ***")

if __name__=="__main__": main()
