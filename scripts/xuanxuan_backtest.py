"""xuanxuan_backtest.py — backtest xuanxuan008's ACTUAL strategy from his REAL fills.

No assumed fill model. Pull his real trades (data-api /activity), group by BTC-5m window,
reconstruct per-window: Up buy/sell shares+cost, Down buy/sell, then settle with the REAL
market outcome (gamma outcomePrices). PnL = net_winner_shares*1 + sell_proceeds - buy_cost.
(MERGE of a matched pair == holding it to settlement == $1/pair, so ignoring merges is exact.)

This is the truest possible answer to "does his two-sided arb actually make money".
Usage: python xuanxuan_backtest.py [n_windows]
"""
import httpx, json, sys, time, statistics
from collections import defaultdict

X="0xcfb103c37c0234f524c632d964ed31f117b5f694"  # xuanxuan008 / 0xcfb103
DATA="https://data-api.polymarket.com"
GAMMA="https://gamma-api.polymarket.com/markets"

def pull_activity(c, pages=8, per=500):
    acts=[]
    for i in range(pages):
        try:
            r=c.get(f"{DATA}/activity",params={"user":X,"limit":per,"offset":i*per})
            a=r.json()
        except Exception as e:
            print(f"  activity page {i} err {e}"); break
        if not isinstance(a,list) or not a: break
        acts.extend(a)
        if len(a)<per: break
    return acts

def winner_for(c, slug, cache):
    if slug in cache: return cache[slug]
    res=None
    try:
        arr=c.get(GAMMA,params={"slug":slug}).json()
        if arr:
            m=arr[0]
            if m.get("closed") or m.get("umaResolutionStatuses"):
                outs=json.loads(m.get("outcomes","[]")); prices=json.loads(m.get("outcomePrices","[]"))
                if prices and outs:
                    pf=[float(x) for x in prices]
                    if max(pf)>=0.99:  # resolved
                        res=outs[pf.index(max(pf))]
    except Exception:
        pass
    cache[slug]=res; return res

def main():
    want=int(sys.argv[1]) if len(sys.argv)>1 else 60
    c=httpx.Client(timeout=30)
    print(f"pulling xuanxuan008 activity ...")
    acts=pull_activity(c)
    print(f"  got {len(acts)} activity rows")
    # group TRADE rows by slug, only btc-updown-5m
    wins=defaultdict(lambda: defaultdict(lambda:[0.0,0.0]))  # slug -> outcome -> [shares,usdc]
    meta={}
    for a in acts:
        if a.get("type")!="TRADE": continue
        slug=a.get("slug","")
        if "updown-5m" not in slug: continue
        o=a.get("outcome"); side=a.get("side");
        try: sh=float(a.get("size",0)); pr=float(a.get("price",0))
        except: continue
        if o not in ("Up","Down") or side not in ("BUY","SELL"): continue
        usdc=sh*pr
        if side=="BUY":
            wins[slug][o][0]+=sh; wins[slug][o][1]+=usdc
        else:
            wins[slug][o][0]-=sh; wins[slug][o][1]-=usdc  # sell: reduce net shares & net cost
        meta[slug]=a.get("conditionId")
    # sort newest windows first by start ts in slug
    def startts(s):
        try: return int(s.rsplit("-",1)[1])
        except: return 0
    slugs=sorted(wins.keys(), key=startts, reverse=True)[:want]
    print(f"  {len(wins)} updown-5m windows traded; backtesting newest {len(slugs)}\n")
    cache={}; res=[]
    for slug in slugs:
        w=wins[slug]
        up_sh,up_cost=w["Up"]; dn_sh,dn_cost=w["Down"]
        winner=winner_for(c,slug,cache)
        if winner is None: continue  # not resolved / unknown
        settle = (up_sh if winner=="Up" else dn_sh)*1.0
        cost = up_cost+dn_cost
        pnl = settle - cost
        matched=min(max(up_sh,0),max(dn_sh,0))
        comb=((up_cost/up_sh)+(dn_cost/dn_sh)) if (up_sh>0.01 and dn_sh>0.01) else None
        res.append({"slug":slug,"winner":winner,"up":round(up_sh,1),"dn":round(dn_sh,1),
                    "imb":round(abs(up_sh-dn_sh),1),"comb":round(comb,4) if comb else None,
                    "cost":round(cost,2),"pnl":round(pnl,3),"matched":round(matched,1)})
    if not res:
        print("no resolved windows found"); return
    print(f"  {'slug':<26}{'win':<5}{'up':>7}{'dn':>7}{'imb':>6}{'comb':>8}{'cost':>9}{'pnl':>9}")
    for r in res:
        print(f"  {r['slug'][-24:]:<26}{r['winner']:<5}{r['up']:>7}{r['dn']:>7}{r['imb']:>6}"
              f"{(r['comb'] if r['comb'] else 0):>8.4f}{r['cost']:>9.2f}{r['pnl']:>+9.3f}")
    tot=sum(r["pnl"] for r in res); cost=sum(r["cost"] for r in res)
    combs=[r["comb"] for r in res if r["comb"]]
    wins_n=sum(1 for r in res if r["pnl"]>0)
    print(f"\n  resolved windows: {len(res)} | win-rate(profitable): {100*wins_n//len(res)}%")
    print(f"  median combined cost (matched windows): {statistics.median(combs):.4f}  (<1.0 = real arb edge)")
    print(f"  avg imbalance: {sum(r['imb'] for r in res)/len(res):.1f}sh")
    print(f"  total deployed: ${cost:.0f} | total PnL: ${tot:+.2f}")
    print(f"  *** NET: {100*tot/max(cost,1):+.3f}% per $ deployed  (his REAL fills, REAL outcomes) ***")

if __name__=="__main__": main()
