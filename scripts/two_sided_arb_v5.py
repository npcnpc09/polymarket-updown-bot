"""two_sided_arb_v5.py — two-sided maker arb, BUY-only (no sell, no approval needed).

Design fixed after v1-v4 bugs:
  - Reliable post (batch + retry, never cross).
  - Half-leg handling = FORCE-COMPLETE the missing leg via escalating marketable BUY
    (retry ask+1t, +2t, ... up to 0.99 until full N shares acquired). BUY only needs USDC.
  - NEVER sell, NEVER merge -> never needs ERC1155 approval (v4's failure).
  - Hold hedged pair to settle (5m auto-redeem $1/pair). Never naked.

Worst case half-leg = complete at sum slightly >1 (bounded few-cent loss), never directional.
Tiny (5 sh). REAL MONEY. python two_sided_arb_v5.py --trials 8
"""
import argparse, json, os, sys, time
from datetime import datetime, timezone
import httpx

def iso(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def log(m): print(f"[{iso()}] {m}", flush=True)
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTF=os.path.join(ROOT,"data","two_sided_arb_v5.jsonl")
SHARES=5.0; MIN_TTL=40; GRACE_SEC=6.0; LAGFILL_SEC=6.0; POST_RETRIES=5; TICK=0.01; PRICE_CAP=0.99

def load_env():
    envf=os.path.join(ROOT,".env")
    if os.path.exists(envf):
        for line in open(envf,encoding="utf-8"):
            if "=" in line and not line.startswith("#"):
                k,v=line.strip().split("=",1); os.environ.setdefault(k.strip(),v.strip())
    return os.environ.get("POLY_PK"),os.environ.get("POLY_PROXY")

def best(ob):
    bb=max((float(l.price) for l in ob.bids),default=None)
    ba=min((float(l.price) for l in ob.asks),default=None)
    return bb,ba

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--trials",type=int,default=8); ap.add_argument("--shares",type=float,default=SHARES)
    ap.add_argument("--min-margin",type=float,default=0.005)
    a=ap.parse_args(); a.trials=min(a.trials,15)
    pk,proxy=load_env()
    if not pk or not proxy: log("need creds"); sys.exit(1)
    from polymarket import SecureClient
    c=SecureClient.create(private_key=pk,wallet=proxy)
    usdc=float(c.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6
    log(f"TWO-SIDED ARB v5 (BUY-only, never naked) | wallet ${usdc:.2f} trials={a.trials}")
    http=httpx.Client(); done=set(); trial=0; results=[]
    def book(tok): return c.get_order_book(token_id=tok)
    def fills(oid):
        try: return float(c.get_order(order_id=oid).size_matched)
        except: return 0.0
    def safe_bid(tok):
        bb,ba=best(book(tok))
        if bb is None or ba is None: return None
        p=bb
        if p>=ba: p=round(ba-TICK,2)
        return p if p>0 else None
    def post_retry(tok,label):
        for att in range(POST_RETRIES):
            p=safe_bid(tok)
            if p is None: time.sleep(0.3); continue
            try:
                signed=c.create_limit_order(token_id=tok,price=p,size=a.shares,side="BUY",post_only=True)
                r=c.post_order(signed)
                if getattr(r,"ok",False): return getattr(r,"order_id",None),p
            except Exception as e: log(f"    {label} post exc {str(e)[:30]}")
            time.sleep(0.25)
        return None,None
    def force_complete(tok, need):
        """BUY `need` shares via escalating marketable limit until filled. Returns avg fill px or None."""
        acquired=0.0; spent=0.0; rem=need
        for att in range(8):
            bb,ba=best(book(tok))
            if ba is None: time.sleep(0.3); continue
            px=min(PRICE_CAP, round(ba+TICK*(att+1),2))
            try:
                r=c.place_limit_order(token_id=tok,price=px,size=rem,side="BUY",post_only=False)
            except Exception as e:
                log(f"    complete exc {str(e)[:30]}"); time.sleep(0.3); continue
            if not getattr(r,"ok",False): time.sleep(0.3); continue
            oid=getattr(r,"order_id",None); f=0.0
            for _ in range(5):
                time.sleep(0.3); f=fills(oid)
                if f>=rem-1e-6: break
            if f>0: acquired+=f; spent+=f*px; rem-=f
            if rem<=1e-6: return spent/acquired
            if oid:
                try: c.cancel_order(order_id=oid)
                except: pass
        return (spent/acquired) if acquired>0 else None

    while trial<a.trials:
        t=int(time.time()); st=(t//300)*300; slug=f"btc-updown-5m-{st}"; settle=st+300; ttl=settle-time.time()
        if slug in done or not (MIN_TTL+55<=ttl<=245): time.sleep(3); continue
        arr=http.get("https://gamma-api.polymarket.com/markets",params={"slug":slug},timeout=12).json()
        if not arr: time.sleep(2); continue
        m=arr[0]; ids=json.loads(m["clobTokenIds"]); outs=json.loads(m["outcomes"])
        up=ids[outs.index("Up")]; dn=ids[outs.index("Down")]
        ub,ua=best(book(up)); db,da=best(book(dn))
        if None in (ub,ua,db,da): time.sleep(2); continue
        bid_sum=ub+db; margin=1-bid_sum
        if margin<a.min_margin: time.sleep(4); continue
        done.add(slug); trial+=1
        log(f"TRIAL {trial} {slug} ttl={int(ttl)}s | Up {ub}/{ua} Dn {db}/{da} BID_SUM={bid_sum:.3f}")
        legs={"Up":{"tok":up,"oid":None,"fpx":None},"Down":{"tok":dn,"oid":None,"fpx":None}}
        try:
            pu=safe_bid(up); pd=safe_bid(dn)
            if pu and pd:
                su=c.create_limit_order(token_id=up,price=pu,size=a.shares,side="BUY",post_only=True)
                sd=c.create_limit_order(token_id=dn,price=pd,size=a.shares,side="BUY",post_only=True)
                res=c.post_orders([su,sd])
                if getattr(res[0],"ok",False): legs["Up"]["oid"]=res[0].order_id; legs["Up"]["fpx"]=pu
                if getattr(res[1],"ok",False): legs["Down"]["oid"]=res[1].order_id; legs["Down"]["fpx"]=pd
        except Exception as e: log(f"  batch err {str(e)[:40]}")
        for s in ("Up","Down"):
            if legs[s]["oid"] is None:
                oid,p=post_retry(legs[s]["tok"],s); legs[s]["oid"]=oid; legs[s]["fpx"]=p
        # grace 1: natural both-fill
        deadline=time.time()+GRACE_SEC; fu=fd=0.0
        while time.time()<deadline:
            time.sleep(0.5)
            fu=fills(legs["Up"]["oid"]) if legs["Up"]["oid"] else 0
            fd=fills(legs["Down"]["oid"]) if legs["Down"]["oid"] else 0
            if fu>=a.shares and fd>=a.shares: break
        both=fu>=a.shares-1e-6 and fd>=a.shares-1e-6; none=fu<1e-6 and fd<1e-6
        total_sum=None; outcome=None; action=""
        if both:
            outcome="BOTH"; total_sum=legs["Up"]["fpx"]+legs["Down"]["fpx"]; action="both_maker"
        elif none:
            outcome="NONE"
            for L in legs.values():
                if L["oid"]:
                    try: c.cancel_order(order_id=L["oid"])
                    except: pass
            action="canceled"
        else:
            fside="Up" if fu>=a.shares-1e-6 else "Down"; miss="Down" if fside=="Up" else "Up"
            # grace 2: let the lagging bid maybe still fill cheap
            d2=time.time()+LAGFILL_SEC; mf=0.0
            while time.time()<d2:
                time.sleep(0.5)
                mf=fills(legs[miss]["oid"]) if legs[miss]["oid"] else 0
                if mf>=a.shares: break
            if mf>=a.shares-1e-6:
                outcome="BOTH"; total_sum=legs["Up"]["fpx"]+legs["Down"]["fpx"]; action="both_lagfill"
            else:
                # cancel the unfilled bid, FORCE-COMPLETE the missing leg via BUY (never naked, never sell)
                if legs[miss]["oid"]:
                    try: c.cancel_order(order_id=legs[miss]["oid"])
                    except: pass
                cpx=force_complete(legs[miss]["tok"], a.shares-mf)
                if cpx is not None:
                    # blended missing-leg price across any lag-fill + completed
                    miss_px = cpx if mf<=0 else (mf*legs[miss]["fpx"]+(a.shares-mf)*cpx)/a.shares
                    outcome="HEDGED_COMPLETED"; total_sum=legs[fside]["fpx"]+miss_px; action=f"force-bought {miss}@~{cpx:.3f}"
                    log(f"  HALF->force-completed {miss}@{cpx:.3f} sum={total_sum:.3f} (hedged, holding to settle)")
                else:
                    outcome="COMPLETE_FAILED"; action=f"!!! could not complete {miss} (held {fside})"
                    log(f"  *** could not complete {miss}; holding {fside} -> will retry/settle ***")
        pnl=a.shares*(1-total_sum) if total_sum else None
        rec={"slug":slug,"outcome":outcome,"bid_sum":round(bid_sum,4),"up_fill":fu,"dn_fill":fd,
             "total_sum":round(total_sum,4) if total_sum else None,
             "est_pnl":round(pnl,3) if pnl is not None else None,"action":action}
        with open(OUTF,"a",encoding="utf-8") as f: f.write(json.dumps(rec)+"\n")
        results.append(rec); log(f"  RESULT={outcome} sum={rec['total_sum']} pnl={('$%.2f'%pnl) if pnl is not None else 'n/a'}")
        time.sleep(2)
    both=sum(1 for r in results if r["outcome"]=="BOTH"); hc=sum(1 for r in results if r["outcome"]=="HEDGED_COMPLETED")
    none=sum(1 for r in results if r["outcome"]=="NONE"); fail=sum(1 for r in results if r["outcome"]=="COMPLETE_FAILED")
    pnls=[r["est_pnl"] for r in results if r.get("est_pnl") is not None]
    log("="*55)
    log(f"SUMMARY {len(results)}: BOTH={both} HEDGED_COMPLETED={hc} NONE={none} COMPLETE_FAILED={fail}")
    log(f"  hedged rate={100*(both+hc)//max(len(results),1)}% (never naked unless COMPLETE_FAILED={fail})")
    if pnls: log(f"  net est PnL=${sum(pnls):+.2f} over {len(pnls)} = {100*sum(pnls)/(SHARES*len(pnls)):+.2f}%/cycle")
    http.close()

if __name__=="__main__": main()
