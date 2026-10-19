"""xuanxuan_cashflow.py — xuanxuan008's REALIZED PnL from on-chain cashflows. Zero model.

Per BTC-5m window (conditionId), sum his actual cash:
  cash_out = sum(usdcSize) of BUY trades
  cash_in  = sum(usdcSize) of SELL trades + REDEEM + MERGE/CONVERT
  realized PnL = cash_in - cash_out          <- his ACTUAL profit, no assumptions
Also reconstruct combined buy cost (up_avg + dn_avg) per window = the arb-edge metric.

Usage: python xuanxuan_cashflow.py [n_windows]
"""
import httpx, json, sys, statistics
from collections import defaultdict, Counter

X="0xcfb103c37c0234f524c632d964ed31f117b5f694"
DATA="https://data-api.polymarket.com"

def pull(c, pages=12, per=500):
    acts=[]
    for i in range(pages):
        try: a=c.get(f"{DATA}/activity",params={"user":X,"limit":per,"offset":i*per}).json()
        except Exception as e: print(f"  page {i} err {e}"); break
        if not isinstance(a,list) or not a: break
        acts.extend(a)
        if len(a)<per: break
    return acts

def startts(s):
    try: return int(s.rsplit("-",1)[1])
    except: return 0

def main():
    want=int(sys.argv[1]) if len(sys.argv)>1 else 80
    c=httpx.Client(timeout=30)
    print("pulling xuanxuan008 full activity ...")
    acts=pull(c)
    print(f"  {len(acts)} rows | types: {dict(Counter(a.get('type') for a in acts))}")
    W=defaultdict(lambda:{"slug":None,"out":0.0,"in":0.0,"up_sh":0.0,"up_c":0.0,"dn_sh":0.0,"dn_c":0.0,
                          "redeem":0.0,"merge":0.0,"sell":0.0,"buy":0.0,"n":0})
    for a in acts:
        slug=a.get("slug","")
        if "updown-5m" not in slug: continue
        cid=a.get("conditionId"); w=W[cid]; w["slug"]=slug; w["n"]+=1
        t=a.get("type"); side=a.get("side"); o=a.get("outcome")
        try: usd=float(a.get("usdcSize",0)); sh=float(a.get("size",0)); pr=float(a.get("price",0))
        except: continue
        if t=="TRADE":
            if side=="BUY":
                w["out"]+=usd; w["buy"]+=usd
                if o=="Up": w["up_sh"]+=sh; w["up_c"]+=usd
                elif o=="Down": w["dn_sh"]+=sh; w["dn_c"]+=usd
            elif side=="SELL":
                w["in"]+=usd; w["sell"]+=usd
                if o=="Up": w["up_sh"]-=sh; w["up_c"]-=usd
                elif o=="Down": w["dn_sh"]-=sh; w["dn_c"]-=usd
        elif t=="REDEEM":
            w["in"]+=usd; w["redeem"]+=usd
        elif t in ("MERGE","CONVERT","SPLIT"):
            # MERGE returns $1/pair; SPLIT spends $1/pair (rare). treat by sign of usd.
            w["in"]+=usd; w["merge"]+=usd
    # keep windows that have at least one trade and are "closed out" (redeem or merge present)
    items=[(cid,w) for cid,w in W.items() if w["buy"]>0]
    items.sort(key=lambda kv: startts(kv[1]["slug"]), reverse=True)
    items=items[:want]
    print(f"  {len(W)} updown-5m windows; analyzing newest {len(items)} with buys\n")
    rows=[]
    for cid,w in items:
        pnl=w["in"]-w["out"]
        comb=((w["up_c"]/w["up_sh"])+(w["dn_c"]/w["dn_sh"])) if (w["up_sh"]>0.01 and w["dn_sh"]>0.01) else None
        imb=abs(w["up_sh"]-w["dn_sh"])
        rows.append({"slug":w["slug"],"out":w["out"],"pnl":pnl,"comb":comb,"imb":imb,
                     "up":w["up_sh"],"dn":w["dn_sh"],"redeem":w["redeem"],"merge":w["merge"],"sell":w["sell"]})
    print(f"  {'window':<14}{'up':>7}{'dn':>7}{'imb':>6}{'comb':>8}{'deploy':>9}{'pnl':>9}")
    for r in rows:
        print(f"  {r['slug'].rsplit('-',1)[1]:<14}{r['up']:>7.1f}{r['dn']:>7.1f}{r['imb']:>6.1f}"
              f"{(r['comb'] or 0):>8.4f}{r['out']:>9.2f}{r['pnl']:>+9.3f}")
    tot=sum(r["pnl"] for r in rows); deploy=sum(r["out"] for r in rows)
    combs=[r["comb"] for r in rows if r["comb"]]
    winr=sum(1 for r in rows if r["pnl"]>0)
    # only "fully closed" windows (redeem or merge present) give clean realized PnL
    closed=[r for r in rows if r["redeem"]>0 or r["merge"]>0]
    ctot=sum(r["pnl"] for r in closed); cdep=sum(r["out"] for r in closed)
    print(f"\n  === ALL {len(rows)} windows ===")
    print(f"  profitable windows: {winr}/{len(rows)} = {100*winr//max(len(rows),1)}%")
    if combs: print(f"  median combined buy cost: {statistics.median(combs):.4f}  (<1.0 = genuine arb)")
    print(f"  avg imbalance: {sum(r['imb'] for r in rows)/len(rows):.1f}sh")
    print(f"  total deployed ${deploy:.0f} | total realized PnL ${tot:+.2f} = {100*tot/max(deploy,1):+.3f}%/$ deployed")
    print(f"\n  === {len(closed)} FULLY-CLOSED (redeem/merge present, cleanest) ===")
    if closed:
        cwin=sum(1 for r in closed if r["pnl"]>0)
        print(f"  profitable: {cwin}/{len(closed)} = {100*cwin//len(closed)}%")
        print(f"  total deployed ${cdep:.0f} | realized PnL ${ctot:+.2f} = {100*ctot/max(cdep,1):+.3f}%/$ deployed")
        print(f"  avg PnL/window: ${ctot/len(closed):+.3f}")

if __name__=="__main__": main()
