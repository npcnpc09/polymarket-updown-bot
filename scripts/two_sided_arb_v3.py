"""two_sided_arb_v3.py — two-sided maker arb: RELIABLE posting + anti-half-leg.

v2 revealed the real failure mode: post_only orders get REJECTED ("crosses book")
because the ask drops below our bid in the API round-trip -> only one leg posts ->
half-leg. So v3 fixes the POSTING:
  1. Batch-post both legs (create_limit_order x2 + post_orders) = minimal inter-leg gap.
  2. Construct price = min(best_bid, best_ask - tick) so it never crosses by construction.
  3. RETRY any rejected leg: re-read fresh book, re-sign, re-post (up to N times).
  4. If a leg truly can't post but the other filled -> v2 anti-half-leg (complete or exit).

Goal: drive both-post success -> both-fill -> capture the ~1% arb reliably.
Tiny (5 sh). REAL MONEY. python two_sided_arb_v3.py --trials 8
"""
import argparse, json, os, sys, time
from datetime import datetime, timezone
import httpx

def iso(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def log(m): print(f"[{iso()}] {m}", flush=True)
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTF=os.path.join(ROOT,"data","two_sided_arb_v3.jsonl")
SHARES=5.0; MIN_TTL=35; GRACE_SEC=5.0; COMPLETE_MAX=1.015; POST_RETRIES=5; TICK=0.01

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
    log(f"TWO-SIDED ARB v3 (reliable post + anti-half-leg) | wallet ${usdc:.2f} trials={a.trials}")
    http=httpx.Client(); done=set(); trial=0; results=[]
    def book(tok): return c.get_order_book(token_id=tok)
    def fills(oid):
        try: return float(c.get_order(order_id=oid).size_matched)
        except: return 0.0
    def safe_price(tok):
        bb,ba=best(book(tok))
        if bb is None or ba is None: return None
        p=bb
        if p>=ba: p=round(ba-TICK,2)
        return p if p>0 else None
    def post_retry(tok, label):
        for att in range(POST_RETRIES):
            p=safe_price(tok)
            if p is None: time.sleep(0.3); continue
            try:
                signed=c.create_limit_order(token_id=tok,price=p,size=a.shares,side="BUY",post_only=True)
                r=c.post_order(signed)
                if getattr(r,"ok",False): return getattr(r,"order_id",None),p
                code=getattr(r,"code","")
                log(f"    {label} rejected ({code}) att{att+1}, retry@fresh")
            except Exception as e:
                log(f"    {label} post exc att{att+1}: {str(e)[:40]}")
            time.sleep(0.25)
        return None,None

    while trial<a.trials:
        t=int(time.time()); st=(t//300)*300; slug=f"btc-updown-5m-{st}"; settle=st+300; ttl=settle-time.time()
        if slug in done or not (MIN_TTL+50<=ttl<=250): time.sleep(3); continue
        arr=http.get("https://gamma-api.polymarket.com/markets",params={"slug":slug},timeout=12).json()
        if not arr: time.sleep(2); continue
        m=arr[0]; ids=json.loads(m["clobTokenIds"]); outs=json.loads(m["outcomes"])
        up=ids[outs.index("Up")]; dn=ids[outs.index("Down")]
        ub,ua=best(book(up)); db,da=best(book(dn))
        if None in (ub,ua,db,da): time.sleep(2); continue
        bid_sum=ub+db; margin=1-bid_sum
        if margin<a.min_margin: time.sleep(4); continue
        done.add(slug); trial+=1
        log(f"TRIAL {trial} {slug} ttl={int(ttl)}s | Up {ub}/{ua} Dn {db}/{da} BID_SUM={bid_sum:.3f} margin={100*margin:.1f}%")
        legs={"Up":{"tok":up,"oid":None,"fpx":None},"Down":{"tok":dn,"oid":None,"fpx":None}}
        # --- attempt 1: batch both ---
        try:
            pu=safe_price(up); pd=safe_price(dn)
            if pu and pd:
                su=c.create_limit_order(token_id=up,price=pu,size=a.shares,side="BUY",post_only=True)
                sd=c.create_limit_order(token_id=dn,price=pd,size=a.shares,side="BUY",post_only=True)
                res=c.post_orders([su,sd])
                if getattr(res[0],"ok",False): legs["Up"]["oid"]=res[0].order_id; legs["Up"]["fpx"]=pu
                if getattr(res[1],"ok",False): legs["Down"]["oid"]=res[1].order_id; legs["Down"]["fpx"]=pd
        except Exception as e:
            log(f"  batch err {str(e)[:50]}")
        # --- retry any leg that didn't post ---
        for s in ("Up","Down"):
            if legs[s]["oid"] is None:
                oid,p=post_retry(legs[s]["tok"], s)
                legs[s]["oid"]=oid; legs[s]["fpx"]=p
        posted=[s for s in legs if legs[s]["oid"]]
        log(f"  posted legs: {posted} @ {[legs[s]['fpx'] for s in posted]}")
        # --- grace window for fills ---
        deadline=time.time()+GRACE_SEC; fu=fd=0.0
        while time.time()<deadline:
            time.sleep(0.5)
            if legs["Up"]["oid"]: fu=fills(legs["Up"]["oid"])
            if legs["Down"]["oid"]: fd=fills(legs["Down"]["oid"])
            if fu>=a.shares and fd>=a.shares: break
        both=fu>=a.shares-1e-6 and fd>=a.shares-1e-6
        none=fu<1e-6 and fd<1e-6
        total_sum=None; action="both_hold"
        if both:
            outcome="BOTH"; total_sum=legs["Up"]["fpx"]+legs["Down"]["fpx"]
        elif none:
            outcome="NONE"
            for L in legs.values():
                if L["oid"]:
                    try: c.cancel_order(order_id=L["oid"])
                    except: pass
            action="canceled"
        else:
            outcome="HALF"
            fside="Up" if fu>=a.shares-1e-6 else "Down"; miss="Down" if fside=="Up" else "Up"
            if legs[miss]["oid"]:
                try: c.cancel_order(order_id=legs[miss]["oid"])
                except: pass
            mb,ma=best(book(legs[miss]["tok"]))
            comp=(legs[fside]["fpx"]+ma) if ma else 99
            if ma and comp<=COMPLETE_MAX:
                try:
                    mr=c.place_market_order(token_id=legs[miss]["tok"],side="BUY",shares=a.shares,order_type="FAK")
                    mk=getattr(mr,"making_amount",None); tk=getattr(mr,"taking_amount",None)
                    cpx=(float(mk)/float(tk)) if (mk and tk and float(tk)>0) else ma
                    total_sum=legs[fside]["fpx"]+cpx; action=f"completed {miss}@{cpx:.3f}"
                    log(f"  HALF->completed {miss}@{cpx:.3f} sum={total_sum:.3f}")
                except Exception as e: action=f"complete_err {str(e)[:30]}"
            else:
                try:
                    sr=c.place_market_order(token_id=legs[fside]["tok"],side="SELL",shares=a.shares,order_type="FAK")
                    mk=getattr(sr,"making_amount",None); tk=getattr(sr,"taking_amount",None)
                    spx=(float(tk)/float(mk)) if (mk and tk and float(mk)>0) else mb
                    loss=(legs[fside]["fpx"]-spx)*a.shares
                    rec={"slug":slug,"outcome":"HALF_EXIT","bid_sum":round(bid_sum,4),"loss":round(loss,3),"action":f"exit {fside}@{spx:.3f}"}
                    with open(OUTF,"a",encoding="utf-8") as f: f.write(json.dumps(rec)+"\n")
                    results.append(rec); log(f"  HALF->EXIT {fside}@{spx:.3f} loss=${loss:.2f}"); time.sleep(2); continue
                except Exception as e: action=f"exit_err {str(e)[:30]}"
        pnl=a.shares*(1-total_sum) if total_sum else None
        rec={"slug":slug,"outcome":outcome,"bid_sum":round(bid_sum,4),"up_fill":fu,"dn_fill":fd,
             "total_sum":round(total_sum,4) if total_sum else None,"est_pnl":round(pnl,3) if pnl is not None else None,"action":action}
        with open(OUTF,"a",encoding="utf-8") as f: f.write(json.dumps(rec)+"\n")
        results.append(rec); log(f"  RESULT={outcome} sum={rec['total_sum']} pnl={('$%.2f'%pnl) if pnl is not None else 'n/a'}")
        time.sleep(2)
    both=sum(1 for r in results if r["outcome"]=="BOTH"); half=sum(1 for r in results if str(r["outcome"]).startswith("HALF")); none=sum(1 for r in results if r["outcome"]=="NONE")
    pnls=[r.get("est_pnl") for r in results if r.get("est_pnl") is not None]; losses=[r.get("loss") for r in results if r.get("loss") is not None]
    net=sum(pnls)-sum(losses)
    log("="*55)
    log(f"SUMMARY {len(results)}: BOTH={both} HALF={half} NONE={none} | both-fill={100*both//max(len(results),1)}%")
    log(f"  net est PnL=${net:+.2f} | arbs:+${sum(pnls):.2f} half-leg losses:-${sum(losses):.2f}")
    http.close()

if __name__=="__main__": main()
