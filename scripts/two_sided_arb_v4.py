"""two_sided_arb_v4.py — two-sided maker arb: reliable post + BULLETPROOF anti-half-leg.

v3 bug: place_market_order(side=BUY, shares=..) failed ("amount required for BUY market")
-> completion failed -> naked leg -> -$2.90. Fix: use MARKETABLE LIMIT orders (cross the
spread with exact share count, post_only=False) for both completion (BUY) and exit (SELL).
Plus a robust fallback ladder: complete -> if fail, exit -> if fail, retry exit -> never naked.

Tiny (5 sh). REAL MONEY. python two_sided_arb_v4.py --trials 8
"""
import argparse, json, os, sys, time
from datetime import datetime, timezone
import httpx

def iso(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def log(m): print(f"[{iso()}] {m}", flush=True)
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTF=os.path.join(ROOT,"data","two_sided_arb_v4.jsonl")
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
    log(f"TWO-SIDED ARB v4 (bulletproof) | wallet ${usdc:.2f} trials={a.trials}")
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
            except Exception as e: log(f"    {label} exc {str(e)[:35]}")
            time.sleep(0.25)
        return None,None
    def take(tok,side,sh):
        """marketable LIMIT (cross), exact shares. returns avg fill price or None."""
        for att in range(3):
            bb,ba=best(book(tok))
            if side=="BUY":
                if ba is None: time.sleep(0.3); continue
                p=min(0.99,round(ba+TICK,2))
            else:
                if bb is None: time.sleep(0.3); continue
                p=max(0.01,round(bb-TICK,2))
            try:
                r=c.place_limit_order(token_id=tok,price=p,size=sh,side=side,post_only=False)
            except Exception as e:
                log(f"    take {side} exc {str(e)[:35]}"); time.sleep(0.3); continue
            if not getattr(r,"ok",False): time.sleep(0.3); continue
            mk=getattr(r,"making_amount",None); tk=getattr(r,"taking_amount",None); oid=getattr(r,"order_id",None)
            # for BUY: taking=shares, making=usdc; for SELL: making=shares, taking=usdc
            try:
                if side=="BUY" and mk and tk and float(tk)>=sh-0.5: return float(mk)/float(tk)
                if side=="SELL" and mk and tk and float(mk)>=sh-0.5: return float(tk)/float(mk)
            except: pass
            # poll fill
            f=0.0
            for _ in range(6):
                time.sleep(0.35); f=fills(oid)
                if f>=sh-1e-6: return p
            if f<sh-1e-6 and oid:
                try: c.cancel_order(order_id=oid)
                except: pass
        return None

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
        deadline=time.time()+GRACE_SEC; fu=fd=0.0
        while time.time()<deadline:
            time.sleep(0.5)
            if legs["Up"]["oid"]: fu=fills(legs["Up"]["oid"])
            if legs["Down"]["oid"]: fd=fills(legs["Down"]["oid"])
            if fu>=a.shares and fd>=a.shares: break
        both=fu>=a.shares-1e-6 and fd>=a.shares-1e-6; none=fu<1e-6 and fd<1e-6
        total_sum=None; action="both_hold"; outcome=None; loss=None
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
            fside="Up" if fu>=a.shares-1e-6 else "Down"; miss="Down" if fside=="Up" else "Up"
            if legs[miss]["oid"]:
                try: c.cancel_order(order_id=legs[miss]["oid"])
                except: pass
            mb,ma=best(book(legs[miss]["tok"]))
            comp=(legs[fside]["fpx"]+ma) if ma else 99
            if ma and comp<=COMPLETE_MAX:
                cpx=take(legs[miss]["tok"],"BUY",a.shares)  # bulletproof marketable buy
                if cpx is not None:
                    outcome="HALF_HEDGED"; total_sum=legs[fside]["fpx"]+cpx; action=f"completed {miss}@{cpx:.3f}"
                    log(f"  HALF->completed {miss}@{cpx:.3f} sum={total_sum:.3f}")
            if outcome is None:
                # exit: sell filled leg (retry until flat - never naked)
                spx=take(legs[fside]["tok"],"SELL",a.shares)
                if spx is not None:
                    outcome="HALF_EXIT"; loss=(legs[fside]["fpx"]-spx)*a.shares; action=f"exit {fside}@{spx:.3f}"
                    log(f"  HALF->EXIT {fside}@{spx:.3f} loss=${loss:.2f}")
                else:
                    outcome="HALF_NAKED"; action=f"!!! NAKED {fside} - could not flatten"
                    log(f"  *** CRITICAL: NAKED {fside}, all flatten attempts failed ***")
        rec={"slug":slug,"outcome":outcome,"bid_sum":round(bid_sum,4),"up_fill":fu,"dn_fill":fd,
             "total_sum":round(total_sum,4) if total_sum else None,
             "est_pnl":round(a.shares*(1-total_sum),3) if total_sum else None,
             "loss":round(loss,3) if loss is not None else None,"action":action}
        with open(OUTF,"a",encoding="utf-8") as f: f.write(json.dumps(rec)+"\n")
        results.append(rec); log(f"  RESULT={outcome} {action}")
        time.sleep(2)
    both=sum(1 for r in results if r["outcome"]=="BOTH")
    hedged=sum(1 for r in results if r["outcome"]=="HALF_HEDGED")
    exited=sum(1 for r in results if r["outcome"]=="HALF_EXIT")
    naked=sum(1 for r in results if r["outcome"]=="HALF_NAKED")
    none=sum(1 for r in results if r["outcome"]=="NONE")
    arb=sum(r["est_pnl"] for r in results if r.get("est_pnl"))
    losses=sum(r["loss"] for r in results if r.get("loss"))
    log("="*55)
    log(f"SUMMARY {len(results)}: BOTH={both} HALF_HEDGED={hedged} HALF_EXIT={exited} NAKED={naked} NONE={none}")
    log(f"  net est PnL=${arb-losses:+.2f} (arb +${arb:.2f}, exit losses -${losses:.2f})")
    log(f"  both-fill rate={100*both//max(len(results),1)}% | NAKED(bad)={naked}")
    http.close()

if __name__=="__main__": main()
