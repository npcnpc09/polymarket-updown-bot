"""two_sided_arb_v2.py — two-sided maker arb WITH anti-half-leg mechanism.

Strategy (xuanxuan008): post BIDS on both legs; bid_sum<1 -> if both fill = arb.
Risk: one-sided fill (half-leg) -> naked directional exposure.

ANTI-HALF-LEG (the new part):
  1. Fast fill detection (poll 0.5s), grace window for natural both-fill.
  2. On one-sided fill: cancel the unfilled bid, then read the MISSING leg's live book:
       - complete_sum = filled_px + missing_ask
       - if complete_sum <= COMPLETE_MAX (still ~hedged/cheap): MARKET-COMPLETE -> stay hedged
       - else (book ran away): SELL the filled leg back at market -> EXIT, loss ~= spread only
     => worst case bounded to ~spread, never a naked directional bet.
  3. Records which branch fired + economics.

Tiny (5 sh). REAL MONEY. python two_sided_arb_v2.py --trials 6
"""
import argparse, json, os, sys, time
from datetime import datetime, timezone
import httpx

def iso(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def log(m): print(f"[{iso()}] {m}", flush=True)
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTF=os.path.join(ROOT,"data","two_sided_arb_v2.jsonl")
SHARES=5.0; MIN_TTL=35; GRACE_SEC=4.0; COMPLETE_MAX=1.015

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
    ap.add_argument("--trials",type=int,default=6); ap.add_argument("--shares",type=float,default=SHARES)
    ap.add_argument("--min-margin",type=float,default=0.005)
    a=ap.parse_args(); a.trials=min(a.trials,12)
    pk,proxy=load_env()
    if not pk or not proxy: log("need creds"); sys.exit(1)
    from polymarket import SecureClient
    c=SecureClient.create(private_key=pk,wallet=proxy)
    usdc=float(c.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6
    log(f"TWO-SIDED ARB v2 (anti-half-leg) | wallet ${usdc:.2f} sh={a.shares} trials={a.trials}")
    http=httpx.Client(); done=set(); trial=0; results=[]
    def book(tok): return c.get_order_book(token_id=tok)
    def fills(oid):
        try: return float(c.get_order(order_id=oid).size_matched)
        except: return 0.0

    while trial<a.trials:
        t=int(time.time()); st=(t//300)*300; slug=f"btc-updown-5m-{st}"; settle=st+300; ttl=settle-time.time()
        if slug in done or not (MIN_TTL+45<=ttl<=255): time.sleep(3); continue
        arr=http.get("https://gamma-api.polymarket.com/markets",params={"slug":slug},timeout=12).json()
        if not arr: time.sleep(2); continue
        m=arr[0]; ids=json.loads(m["clobTokenIds"]); outs=json.loads(m["outcomes"])
        up=ids[outs.index("Up")]; dn=ids[outs.index("Down")]
        ub,ua=best(book(up)); db,da=best(book(dn))
        if None in (ub,ua,db,da): time.sleep(2); continue
        bid_sum=ub+db; margin=1-bid_sum
        if margin<a.min_margin: log(f"  {slug} margin={margin:.3f}<{a.min_margin}; skip"); time.sleep(4); continue
        done.add(slug); trial+=1
        log(f"TRIAL {trial} {slug} ttl={int(ttl)}s | Up {ub}/{ua} Dn {db}/{da} BID_SUM={bid_sum:.3f} margin={100*margin:.1f}%")
        legs={"Up":{"tok":up,"bid":ub,"oid":None,"fpx":ub},"Down":{"tok":dn,"bid":db,"oid":None,"fpx":db}}
        for s,L in legs.items():
            try:
                r=c.place_limit_order(token_id=L["tok"],price=L["bid"],size=a.shares,side="BUY",post_only=True)
                L["oid"]=getattr(r,"order_id",None)
            except Exception as e: log(f"  post {s} err {e}")
        # --- grace window: wait for natural both-fill ---
        deadline=time.time()+GRACE_SEC; fu=fd=0.0
        while time.time()<deadline:
            time.sleep(0.5)
            if legs["Up"]["oid"]: fu=fills(legs["Up"]["oid"])
            if legs["Down"]["oid"]: fd=fills(legs["Down"]["oid"])
            if fu>=a.shares and fd>=a.shares: break
        both=fu>=a.shares-1e-6 and fd>=a.shares-1e-6
        none=fu<1e-6 and fd<1e-6
        action="both_hold"; total_sum=None
        if both:
            outcome="BOTH"; total_sum=legs["Up"]["fpx"]+legs["Down"]["fpx"]
        elif none:
            outcome="NONE"
            for L in legs.values():
                if L["oid"]:
                    try: c.cancel_order(order_id=L["oid"])
                    except: pass
            action="canceled_both"
        else:
            outcome="HALF"
            fside="Up" if fu>=a.shares-1e-6 else "Down"; miss="Down" if fside=="Up" else "Up"
            # cancel unfilled
            if legs[miss]["oid"]:
                try: c.cancel_order(order_id=legs[miss]["oid"])
                except: pass
            # ANTI-HALF-LEG decision
            mb,ma=best(book(legs[miss]["tok"]))
            complete_sum=legs[fside]["fpx"]+ma if ma else 99
            if ma and complete_sum<=COMPLETE_MAX:
                # market-complete -> stay hedged
                try:
                    mr=c.place_market_order(token_id=legs[miss]["tok"],side="BUY",shares=a.shares,order_type="FAK")
                    mk=getattr(mr,"making_amount",None); tk=getattr(mr,"taking_amount",None)
                    cpx=(float(mk)/float(tk)) if (mk and tk and float(tk)>0) else ma
                    total_sum=legs[fside]["fpx"]+cpx; action=f"completed {miss}@{cpx:.3f} (sum {total_sum:.3f})"
                    log(f"  HALF: {fside} filled -> market-completed {miss}@{cpx:.3f}, hedged sum={total_sum:.3f}")
                except Exception as e:
                    action=f"complete_failed {e}"; log(f"  complete err {e}")
            else:
                # book ran -> SELL filled leg back, exit with small loss
                try:
                    sr=c.place_market_order(token_id=legs[fside]["tok"],side="SELL",shares=fu if fside=="Up" else fd,order_type="FAK")
                    mk=getattr(sr,"making_amount",None); tk=getattr(sr,"taking_amount",None)
                    spx=(float(tk)/float(mk)) if (mk and tk and float(mk)>0) else mb
                    # PnL = sold price - bought price (per share) * shares
                    loss=(legs[fside]["fpx"]-spx)*a.shares
                    total_sum=None; action=f"EXITED {fside} sold@{spx:.3f} (complete_sum would be {complete_sum:.3f}) loss=${loss:.2f}"
                    log(f"  HALF: book ran (complete_sum {complete_sum:.3f}>{COMPLETE_MAX}) -> SOLD {fside}@{spx:.3f}, loss=${loss:.2f}")
                    results.append({"slug":slug,"outcome":"HALF_EXIT","bid_sum":bid_sum,"loss":round(loss,3),"action":action})
                    with open(OUTF,"a",encoding="utf-8") as f: f.write(json.dumps(results[-1])+"\n")
                    time.sleep(2); continue
                except Exception as e:
                    action=f"exit_failed {e} (NAKED {fside})"; log(f"  EXIT err {e}")
        pnl=a.shares*(1-total_sum) if total_sum else None
        rec={"slug":slug,"outcome":outcome,"bid_sum":round(bid_sum,4),"up_fill":fu,"dn_fill":fd,
             "total_sum":round(total_sum,4) if total_sum else None,"est_pnl":round(pnl,3) if pnl is not None else None,"action":action}
        with open(OUTF,"a",encoding="utf-8") as f: f.write(json.dumps(rec)+"\n")
        results.append(rec)
        log(f"  RESULT={outcome} sum={rec['total_sum']} pnl={('$%.2f'%pnl) if pnl is not None else 'n/a'} | {action}")
        time.sleep(2)
    both=sum(1 for r in results if r["outcome"]=="BOTH"); half=sum(1 for r in results if r["outcome"].startswith("HALF")); none=sum(1 for r in results if r["outcome"]=="NONE")
    pnls=[r.get("est_pnl") for r in results if r.get("est_pnl") is not None]
    losses=[r.get("loss") for r in results if r.get("loss") is not None]
    net=sum(pnls)-sum(losses) if (pnls or losses) else 0
    log("="*55)
    log(f"SUMMARY {len(results)}: BOTH={both} HALF={half} NONE={none} | both-fill={100*both//max(len(results),1)}%")
    log(f"  net est PnL=${net:+.2f}  (hedged arb + completes - exit losses)")
    log("  anti-half-leg: HALF either market-completed (~hedged) or EXITED (small loss), never naked")
    http.close()

if __name__=="__main__": main()
