"""two_sided_arb_test.py — REAL two-sided maker-arb test (the xuanxuan008 strategy).

Structural fact: Up_ask+Down_ask = 1+spread (>1, no taker arb). BUT Up_bid+Down_bid =
1-spread (<1). So: post BIDS on both legs; if BOTH fill, you bought a $1-redeeming pair
for <$1 = arb (~1-2% on btc 5m). Risk = one-sided fill (half-leg) -> market-complete the
other leg; if the book moved, completion can cost >1 (loss).

Measures over N trials:
  - both-fill rate (= captured arb)
  - one-sided rate -> market-complete economics (sum<1 profit vs >1 loss)
  - net PnL per cycle  (the number that decides if WE can do what xuanxuan008 does)

Tiny: 5 shares/leg. REAL MONEY. python two_sided_arb_test.py --trials 4
"""
import argparse, json, os, sys, time
from datetime import datetime, timezone
import httpx

def iso(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def log(m): print(f"[{iso()}] {m}", flush=True)
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTF=os.path.join(ROOT,"data","two_sided_arb.jsonl")
SHARES=5.0; MIN_TTL=30

def load_env():
    envf=os.path.join(ROOT,".env")
    if os.path.exists(envf):
        for line in open(envf,encoding="utf-8"):
            if "=" in line and not line.startswith("#"):
                k,v=line.strip().split("=",1); os.environ.setdefault(k.strip(),v.strip())
    return os.environ.get("POLY_PK"),os.environ.get("POLY_PROXY")

def win(ob):
    bb=max((float(l.price) for l in ob.bids),default=None)
    ba=min((float(l.price) for l in ob.asks),default=None)
    return bb,ba

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--trials",type=int,default=4); ap.add_argument("--shares",type=float,default=SHARES)
    ap.add_argument("--min-margin",type=float,default=0.005)  # only enter if 1-bid_sum >= this
    a=ap.parse_args(); a.trials=min(a.trials,8)
    pk,proxy=load_env()
    if not pk or not proxy: log("need creds"); sys.exit(1)
    from polymarket import SecureClient
    c=SecureClient.create(private_key=pk,wallet=proxy)
    usdc=float(c.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6
    log(f"TWO-SIDED ARB TEST | wallet ${usdc:.2f} shares={a.shares} trials={a.trials} min_margin={a.min_margin}")
    http=httpx.Client(); done=set(); trial=0; results=[]
    while trial<a.trials:
        t=int(time.time()); st=(t//300)*300; slug=f"btc-updown-5m-{st}"; settle=st+300; ttl=settle-time.time()
        if slug in done or not (MIN_TTL+40<=ttl<=260): time.sleep(3); continue
        arr=http.get("https://gamma-api.polymarket.com/markets",params={"slug":slug},timeout=12).json()
        if not arr: time.sleep(2); continue
        m=arr[0]; ids=json.loads(m["clobTokenIds"]); outs=json.loads(m["outcomes"])
        up=ids[outs.index("Up")]; dn=ids[outs.index("Down")]; cond=m.get("conditionId")
        obu=c.get_order_book(token_id=up); obd=c.get_order_book(token_id=dn)
        ub,ua=win(obu); db,da=win(obd)
        if None in (ub,ua,db,da): time.sleep(2); continue
        bid_sum=ub+db; margin=1-bid_sum
        if margin<a.min_margin:
            log(f"  {slug} bid_sum={bid_sum:.3f} margin={margin:.3f} < {a.min_margin}; skip"); time.sleep(4); continue
        done.add(slug); trial+=1
        log(f"TRIAL {trial} {slug} ttl={int(ttl)}s | Up bid/ask {ub}/{ua} Down {db}/{da} | BID_SUM={bid_sum:.3f} margin={100*margin:.1f}%")
        legs={"Up":{"tok":up,"bid":ub,"ask":ua,"oid":None,"filled":0.0,"fillpx":ub},
              "Down":{"tok":dn,"bid":db,"ask":da,"oid":None,"filled":0.0,"fillpx":db}}
        for side,L in legs.items():
            try:
                r=c.place_limit_order(token_id=L["tok"],price=L["bid"],size=a.shares,side="BUY",post_only=True)
                L["oid"]=getattr(r,"order_id",None)
                log(f"  posted {side} bid @ {L['bid']} ok={getattr(r,'ok',False)} status={getattr(r,'status','?')}")
            except Exception as e:
                log(f"  post {side} err: {e}")
        # poll fills
        while settle-time.time()>MIN_TTL:
            time.sleep(2)
            for side,L in legs.items():
                if L["oid"] and L["filled"]<a.shares:
                    try: L["filled"]=float(c.get_order(order_id=L["oid"]).size_matched)
                    except: pass
            if all(L["filled"]>=a.shares for L in legs.values()): break
        upf=legs["Up"]["filled"]; dnf=legs["Down"]["filled"]
        # classify
        both=upf>=a.shares-1e-6 and dnf>=a.shares-1e-6
        none=upf<1e-6 and dnf<1e-6
        action="hold_hedged"; complete_px=None
        if both:
            outcome="BOTH"; total_sum=legs["Up"]["fillpx"]+legs["Down"]["fillpx"]
        elif none:
            outcome="NONE"; total_sum=None
            for L in legs.values():
                if L["oid"]:
                    try: c.cancel_order(order_id=L["oid"])
                    except: pass
            action="canceled_both"
        else:
            outcome="HALF"
            filled_side="Up" if upf>=a.shares-1e-6 else "Down"
            miss="Down" if filled_side=="Up" else "Up"
            # cancel the unfilled leg
            if legs[miss]["oid"]:
                try: c.cancel_order(order_id=legs[miss]["oid"])
                except: pass
            # MARKET-complete the missing leg
            try:
                mr=c.place_market_order(token_id=legs[miss]["tok"],side="BUY",shares=a.shares,order_type="FAK")
                mk=getattr(mr,"making_amount",None); tk=getattr(mr,"taking_amount",None)
                complete_px=(float(mk)/float(tk)) if (mk and tk and float(tk)>0) else legs[miss]["ask"]
                legs[miss]["fillpx"]=complete_px; legs[miss]["filled"]=a.shares
                action=f"market_completed_{miss}@{complete_px:.3f}"
                log(f"  HALF: {filled_side} filled, market-completed {miss} @ {complete_px:.3f}")
            except Exception as e:
                complete_px=None; action=f"complete_failed (naked {filled_side})"
                log(f"  HALF complete err: {e}")
            total_sum=legs["Up"]["fillpx"]+legs["Down"]["fillpx"] if complete_px else None
        # est PnL (hedged pair redeems $1/pair): pnl = shares*(1 - total_sum)
        pnl = a.shares*(1-total_sum) if total_sum else None
        log(f"  RESULT={outcome} up_fill={upf:.0f} dn_fill={dnf:.0f} total_sum={total_sum} est_pnl={('$%.2f'%pnl) if pnl is not None else 'n/a'}")
        rec={"ts":int(time.time()),"slug":slug,"bid_sum":round(bid_sum,4),"margin":round(margin,4),
             "outcome":outcome,"up_fill":upf,"dn_fill":dnf,"total_sum":round(total_sum,4) if total_sum else None,
             "est_pnl":round(pnl,3) if pnl is not None else None,"action":action}
        with open(OUTF,"a",encoding="utf-8") as f: f.write(json.dumps(rec)+"\n")
        results.append(rec); time.sleep(2)
    # summary
    both=sum(1 for r in results if r["outcome"]=="BOTH"); half=sum(1 for r in results if r["outcome"]=="HALF"); none=sum(1 for r in results if r["outcome"]=="NONE")
    pnls=[r["est_pnl"] for r in results if r["est_pnl"] is not None]
    log("="*55)
    log(f"SUMMARY {len(results)} trials: BOTH={both} HALF={half} NONE={none}")
    log(f"  both-fill rate (arb captured)={100*both//max(len(results),1)}%")
    if pnls: log(f"  net est PnL=${sum(pnls):+.2f} over {len(pnls)} priced trials = {100*sum(pnls)/(SHARES*len(pnls)):+.2f}%/cycle")
    log("  (xuanxuan008 does this at scale for +1.2%/cycle; the q is OUR both-fill rate vs half-leg loss)")
    http.close()

if __name__=="__main__": main()
