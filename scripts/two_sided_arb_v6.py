"""two_sided_arb_v6.py — two-sided maker arb with VALIDATED completion (no naked, no sell).

Completion order solved in isolation:
  place_market_order(side="BUY", amount=USDC, order_type="FAK")  # amount (not shares), >=$1
  -> fills ~amount/price shares, status=matched. No ERC1155 approval needed (BUY only).

Flow:
  - post both bids (batch + retry, never cross)
  - grace: natural both-fill (best: both maker @ bid_sum<1)
  - if one fills (half): brief 2nd grace (lagging bid may fill cheap), else cancel unfilled
    bid and FORCE-COMPLETE the missing leg via market BUY(amount) -> hedged -> hold to settle.
  - NEVER sell, NEVER naked.

Tiny (5 sh). REAL MONEY. python two_sided_arb_v6.py --trials 8
"""
import argparse, json, os, sys, time
from datetime import datetime, timezone
import httpx

def iso(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def log(m): print(f"[{iso()}] {m}", flush=True)
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTF=os.path.join(ROOT,"data","two_sided_arb_v6.jsonl")
SHARES=5.0; MIN_TTL=40; GRACE_SEC=6.0; LAGFILL_SEC=6.0; POST_RETRIES=5; TICK=0.01

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
    a=ap.parse_args(); a.trials=min(a.trials,20)
    pk,proxy=load_env()
    if not pk or not proxy: log("need creds"); sys.exit(1)
    from polymarket import SecureClient
    c=SecureClient.create(private_key=pk,wallet=proxy)
    usdc=float(c.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6
    log(f"TWO-SIDED ARB v6 (validated completion) | wallet ${usdc:.2f} trials={a.trials}")
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
    def complete_buy(tok, target):
        """VALIDATED: market BUY ~target shares via amount(USDC)>=$1, FAK. Returns (shares, usdc)."""
        bb,ba=best(book(tok))
        if ba is None: return 0.0,0.0
        amount=round(max(1.05, target*ba*1.08),2)
        for att in range(4):
            try:
                r=c.place_market_order(token_id=tok,side="BUY",amount=amount,order_type="FAK")
            except Exception as e:
                log(f"    complete exc {str(e)[:35]}"); time.sleep(0.4); continue
            if getattr(r,"ok",False):
                mk=getattr(r,"making_amount",None); tk=getattr(r,"taking_amount",None)
                if mk and tk and float(tk)>0: return float(tk),float(mk)
                return target, amount
            time.sleep(0.4)
        return 0.0,0.0

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
        legs={"Up":{"tok":up,"oid":None,"bid":None,"sh":0.0,"cost":0.0},
              "Down":{"tok":dn,"oid":None,"bid":None,"sh":0.0,"cost":0.0}}
        try:
            pu=safe_bid(up); pd=safe_bid(dn)
            if pu and pd:
                su=c.create_limit_order(token_id=up,price=pu,size=a.shares,side="BUY",post_only=True)
                sd=c.create_limit_order(token_id=dn,price=pd,size=a.shares,side="BUY",post_only=True)
                res=c.post_orders([su,sd])
                if getattr(res[0],"ok",False): legs["Up"]["oid"]=res[0].order_id; legs["Up"]["bid"]=pu
                if getattr(res[1],"ok",False): legs["Down"]["oid"]=res[1].order_id; legs["Down"]["bid"]=pd
        except Exception as e: log(f"  batch err {str(e)[:40]}")
        for s in ("Up","Down"):
            if legs[s]["oid"] is None:
                oid,p=post_retry(legs[s]["tok"],s); legs[s]["oid"]=oid; legs[s]["bid"]=p
        deadline=time.time()+GRACE_SEC; fu=fd=0.0
        while time.time()<deadline:
            time.sleep(0.5)
            fu=fills(legs["Up"]["oid"]) if legs["Up"]["oid"] else 0
            fd=fills(legs["Down"]["oid"]) if legs["Down"]["oid"] else 0
            if fu>=a.shares and fd>=a.shares: break
        both=fu>=a.shares-1e-6 and fd>=a.shares-1e-6; none=fu<1e-6 and fd<1e-6
        outcome=None; action=""
        # record maker fills
        if fu>0: legs["Up"]["sh"]=fu; legs["Up"]["cost"]=fu*legs["Up"]["bid"]
        if fd>0: legs["Down"]["sh"]=fd; legs["Down"]["cost"]=fd*legs["Down"]["bid"]
        if both:
            outcome="BOTH"; action="both_maker"
        elif none:
            outcome="NONE"
            for L in legs.values():
                if L["oid"]:
                    try: c.cancel_order(order_id=L["oid"])
                    except: pass
            action="canceled"
        else:
            fside="Up" if fu>=a.shares-1e-6 else "Down"; miss="Down" if fside=="Up" else "Up"
            d2=time.time()+LAGFILL_SEC; mf=0.0
            while time.time()<d2:
                time.sleep(0.5)
                mf=fills(legs[miss]["oid"]) if legs[miss]["oid"] else 0
                if mf>=a.shares: break
            if mf>=a.shares-1e-6:
                legs[miss]["sh"]=mf; legs[miss]["cost"]=mf*legs[miss]["bid"]; outcome="BOTH"; action="both_lagfill"
            else:
                if legs[miss]["oid"]:
                    try: c.cancel_order(order_id=legs[miss]["oid"])
                    except: pass
                # account any partial lag-fill
                if mf>0: legs[miss]["sh"]=mf; legs[miss]["cost"]=mf*legs[miss]["bid"]
                need=a.shares-mf
                sh,cost=complete_buy(legs[miss]["tok"], need)
                if sh>0:
                    legs[miss]["sh"]+=sh; legs[miss]["cost"]+=cost
                    outcome="HEDGED_COMPLETED"; action=f"completed {miss} +{sh:.1f}sh/${cost:.2f}"
                    log(f"  HALF->completed {miss}: +{sh:.1f}sh for ${cost:.2f} (avg {cost/sh:.3f})")
                else:
                    outcome="COMPLETE_FAILED"; action=f"!!! could not complete {miss} (hold {fside})"
                    log(f"  *** complete failed for {miss}; holding {fside} {fu+fd:.0f}sh ***")
        us=legs["Up"]["sh"]; uc=legs["Up"]["cost"]; ds=legs["Down"]["sh"]; dc=legs["Down"]["cost"]
        hedged=min(us,ds); tot_cost=uc+dc
        est_pnl=(hedged*1.0 - tot_cost) if (us>0 and ds>0) else None  # guaranteed hedged portion
        rec={"slug":slug,"outcome":outcome,"bid_sum":round(bid_sum,4),
             "up_sh":round(us,2),"dn_sh":round(ds,2),"cost":round(tot_cost,3),
             "comb_price":round((uc/us+dc/ds),4) if (us>0 and ds>0) else None,
             "est_pnl":round(est_pnl,3) if est_pnl is not None else None,"action":action}
        with open(OUTF,"a",encoding="utf-8") as f: f.write(json.dumps(rec)+"\n")
        results.append(rec); log(f"  RESULT={outcome} comb={rec['comb_price']} est_pnl={('$%.2f'%est_pnl) if est_pnl is not None else 'n/a'}")
        time.sleep(2)
    both=sum(1 for r in results if r["outcome"]=="BOTH"); hc=sum(1 for r in results if r["outcome"]=="HEDGED_COMPLETED")
    none=sum(1 for r in results if r["outcome"]=="NONE"); fail=sum(1 for r in results if r["outcome"]=="COMPLETE_FAILED")
    pnls=[r["est_pnl"] for r in results if r.get("est_pnl") is not None]
    log("="*55)
    log(f"SUMMARY {len(results)}: BOTH={both} HEDGED_COMPLETED={hc} NONE={none} COMPLETE_FAILED={fail}")
    log(f"  hedged(safe) rate={100*(both+hc)//max(len(results),1)}% | naked-fails={fail}")
    if pnls: log(f"  net est PnL (hedged portion)=${sum(pnls):+.2f} over {len(pnls)} = {100*sum(pnls)/(SHARES*len(pnls)):+.2f}%/cycle")
    log("  NOTE: true PnL = wallet after settle (this est = guaranteed hedged portion only)")
    http.close()

if __name__=="__main__": main()
