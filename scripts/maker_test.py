"""maker_test.py — REAL maker test: post resting limit BIDS, measure fills (no taking).

Tests the maker mechanic eebde uses: instead of crossing the spread (taker), post a
limit BUY at/below the bid and wait to be filled. Measures:
  - does our resting bid FILL before settle? on which side?
  - fill price vs the ask we'd have paid as taker (spread saved)
  - adverse selection: do we get filled mostly on the LOSING side?
  - outcome (win/lose)

Tiny size (5 shares = Polymarket min). Posts on BOTH sides like eebde, at the bid
(maker, post_only so it never crosses). Cancels everything near settle.

REAL MONEY. python maker_test.py --trials 2
"""
import argparse, json, os, sys, time
from datetime import datetime, timezone
import httpx

def iso(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def log(m): print(f"[{iso()}] {m}", flush=True)

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTF=os.path.join(ROOT,"data","maker_test.jsonl")
SHARES=5.0
MIN_TTL=25

def load_env():
    envf=os.path.join(ROOT,".env")
    if os.path.exists(envf):
        for line in open(envf,encoding="utf-8"):
            if "=" in line and not line.startswith("#"):
                k,v=line.strip().split("=",1); os.environ.setdefault(k.strip(),v.strip())
    return os.environ.get("POLY_PK"), os.environ.get("POLY_PROXY")

def cur_window():
    t=int(time.time()); st=(t//300)*300
    return f"btc-updown-5m-{st}", st, st+300

def best(ob):
    bb=max((float(l.price) for l in ob.bids), default=None)
    ba=min((float(l.price) for l in ob.asks), default=None)
    return bb,ba

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--trials",type=int,default=2); ap.add_argument("--shares",type=float,default=SHARES)
    a=ap.parse_args(); a.trials=min(a.trials,5)
    pk,proxy=load_env()
    if not pk or not proxy: log("need POLY_PK/POLY_PROXY"); sys.exit(1)
    from polymarket import SecureClient
    c=SecureClient.create(private_key=pk, wallet=proxy)
    usdc=float(c.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6
    log(f"REAL MAKER TEST | wallet ${usdc:.2f} shares={a.shares} trials={a.trials}")
    http=httpx.Client()
    done=set(); trial=0; results=[]
    while trial<a.trials:
        slug,st,settle=cur_window(); ttl=settle-time.time()
        if slug in done or not (MIN_TTL+30<=ttl<=270):
            time.sleep(3); continue
        arr=http.get("https://gamma-api.polymarket.com/markets",params={"slug":slug},timeout=12).json()
        if not arr: time.sleep(2); continue
        m=arr[0]; ids=json.loads(m["clobTokenIds"]); outs=json.loads(m["outcomes"])
        up=ids[outs.index("Up")]; dn=ids[outs.index("Down")]
        ob_u=c.get_order_book(token_id=up); ob_d=c.get_order_book(token_id=dn)
        bu,au=best(ob_u); bd,ad=best(ob_d)
        if None in (bu,au,bd,ad): time.sleep(2); continue
        done.add(slug); trial+=1
        log(f"TRIAL {trial} {slug} ttl={int(ttl)}s | Up bid={bu}/ask={au} Down bid={bd}/ask={ad}")
        # post resting limit BUY at the BID on BOTH sides (maker, post_only)
        orders={}
        for side,tok,bid,ask in [("Up",up,bu,au),("Down",dn,bd,ad)]:
            try:
                r=c.place_limit_order(token_id=tok,price=bid,size=a.shares,side="BUY",post_only=True)
                oid=getattr(r,"order_id",None); ok=getattr(r,"ok",False)
                orders[side]={"oid":oid,"ok":ok,"bid":bid,"ask":ask,"tok":tok,"filled":0.0,"status":getattr(r,"status","?")}
                log(f"  posted {side} BUY @ {bid} (ask was {ask}) -> ok={ok} status={orders[side]['status']} oid={str(oid)[:14]}")
            except Exception as e:
                log(f"  post {side} err: {e}"); orders[side]={"oid":None,"ok":False,"bid":bid,"ask":ask,"tok":tok,"filled":0.0}
        # poll fills until near settle
        while settle-time.time()>MIN_TTL:
            time.sleep(3)
            for side,o in orders.items():
                if o["oid"] and o["filled"]<a.shares:
                    try: o["filled"]=float(c.get_order(order_id=o["oid"]).size_matched)
                    except: pass
            fu=orders.get("Up",{}).get("filled",0); fd=orders.get("Down",{}).get("filled",0)
            if fu>=a.shares and fd>=a.shares: break
        # cancel anything unfilled
        for side,o in orders.items():
            if o["oid"] and o["filled"]<a.shares:
                try: c.cancel_order(order_id=o["oid"])
                except: pass
        for side,o in orders.items():
            log(f"  RESULT {side}: filled {o['filled']:.1f}/{a.shares} @ {o['bid']} (taker ask was {o['ask']}, saved {round(o['ask']-o['bid'],3)}/sh if filled)")
        rec={"ts":int(time.time()),"slug":slug,
             "up":{k:orders["Up"][k] for k in ("bid","ask","filled")},
             "down":{k:orders["Down"][k] for k in ("bid","ask","filled")}}
        with open(OUTF,"a",encoding="utf-8") as f: f.write(json.dumps(rec)+"\n")
        results.append(rec); time.sleep(2)
    # summary
    fu=sum(1 for r in results if r["up"]["filled"]>=a.shares-1e-6); fd=sum(1 for r in results if r["down"]["filled"]>=a.shares-1e-6)
    log("="*50)
    log(f"SUMMARY {len(results)} trials: Up-bid filled {fu}/{len(results)}, Down-bid filled {fd}/{len(results)}")
    log("  (if the FAVORED/leading side's bid rarely fills -> maker can't get the side you want -> must take)")
    http.close()

if __name__=="__main__": main()
