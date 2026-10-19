"""arb_backtest_hist.py — HISTORICAL backtest of two-sided maker arb from real trade flow.

Pulls ALL trades for many BTC 5m windows (data-api /trades, market=cid). Reconstructs:
  - best bid/ask per side over time (SELL trades print ~at bid, BUY ~at ask)
  - our maker bid fills when cumulative SELL volume on that side at price<=our_bid (after we
    post) exceeds QUEUE+our_size  (QUEUE = assumed book depth ahead; tunable/calibrated)
  - half-leg -> complete missing leg at the prevailing ask (taker)
  - winner from final trade prices
Aggregates over all windows -> both-fill rate, half-leg cost, net PnL/cycle. ZERO real money.

Usage: python arb_backtest_hist.py [n_windows] [queue]
"""
import httpx, json, sys, time, statistics
from collections import defaultdict

X="0xcfb103c37c0234f524c632d964ed31f117b5f694"  # xuanxuan008 (every btc-5m window)
SHARES=5.0; POST_TTL=230; TICK=0.01

def get_window_cids(c, want):
    cids={}
    cursor=None
    for _ in range(6):
        p={"user":X,"limit":500}
        acts=c.get("https://data-api.polymarket.com/activity",params=p).json()
        for a in acts:
            s=a.get("slug","")
            if s.startswith("btc-updown-5m-"): cids[a["conditionId"]]=(s,int(s.rsplit("-",1)[1]))
        if len(cids)>=want: break
        break  # data-api activity not easily paginated here; one pull
    return cids

def main():
    want=int(sys.argv[1]) if len(sys.argv)>1 else 40
    QUEUE=float(sys.argv[2]) if len(sys.argv)>2 else 50.0
    c=httpx.Client(timeout=25)
    cids=get_window_cids(c, want)
    items=sorted(cids.items(), key=lambda kv: kv[1][1])[:want]
    print(f"backtesting {len(items)} btc-5m windows | QUEUE={QUEUE}sh | post@ttl{POST_TTL}\n")
    res=[]
    for cid,(slug,start) in items:
        settle=start+300; post_t=settle-POST_TTL
        try:
            trades=c.get("https://data-api.polymarket.com/trades",params={"market":cid,"limit":1000}).json()
        except: continue
        if not isinstance(trades,list) or len(trades)<10: continue
        trades.sort(key=lambda t:t.get("timestamp",0))
        # reconstruct per-side price refs + winner
        last_px={"Up":None,"Down":None}; final_px={"Up":0.0,"Down":0.0}
        # bid estimate at post: last SELL price before post (sells ~hit bid); ask: last BUY before post
        bid_at_post={"Up":None,"Down":None}; ask_at_post={"Up":None,"Down":None}
        for t in trades:
            o=t.get("outcome"); p=float(t.get("price",0)); ts=t.get("timestamp",0); side=t.get("side")
            if o not in ("Up","Down"): continue
            last_px[o]=p; final_px[o]=p
            if ts<=post_t:
                if side=="SELL": bid_at_post[o]=p
                if side=="BUY": ask_at_post[o]=p
        if None in (last_px["Up"],last_px["Down"]): continue
        winner="Up" if final_px["Up"]>=final_px["Down"] else "Down"
        # our bids: at post, just below mid. use bid estimate or mid-0.005
        def our_bid(o):
            b=bid_at_post[o]; a=ask_at_post[o]
            if b and a: return round((b+a)/2 - 0.005,2)
            ref=b or a or last_px[o]
            return round(ref-0.005,2) if ref else None
        bu=our_bid("Up"); bd=our_bid("Down")
        if bu is None or bd is None or bu<=0 or bd<=0: continue
        bid_sum=bu+bd; margin=1-bid_sum
        # fill model: sell volume after post at price<=our_bid >= QUEUE+SHARES
        sv={"Up":0.0,"Down":0.0}
        for t in trades:
            o=t.get("outcome"); p=float(t.get("price",0)); ts=t.get("timestamp",0); side=t.get("side")
            if o not in ("Up","Down") or ts<post_t or side!="SELL": continue
            our=bu if o=="Up" else bd
            if p<=our+1e-9: sv[o]+=float(t.get("size",0))
        fu=sv["Up"]>=QUEUE+SHARES; fd=sv["Down"]>=QUEUE+SHARES
        # PnL
        if fu and fd:
            outcome="BOTH"; cost=SHARES*bu+SHARES*bd; pnl=SHARES*1.0-cost
        elif fu or fd:
            outcome="HALF"; fside="Up" if fu else "Down"; miss="Down" if fu else "Up"
            fbid=bu if fu else bd
            comp=(ask_at_post[miss] or last_px[miss] or 0.5)+TICK  # complete at ask (taker)
            cost=SHARES*fbid+SHARES*comp; pnl=SHARES*1.0-cost
        else:
            outcome="NONE"; pnl=None; cost=0
        res.append({"slug":slug,"outcome":outcome,"margin":round(margin,3),"pnl":round(pnl,3) if pnl is not None else None,
                    "bid_sum":round(bid_sum,3)})
    from collections import Counter
    oc=Counter(r["outcome"] for r in res)
    print(f"windows: {len(res)} | outcomes: {dict(oc)}")
    both=[r for r in res if r["outcome"]=="BOTH"]; half=[r for r in res if r["outcome"]=="HALF"]
    pnls=[r["pnl"] for r in res if r.get("pnl") is not None]
    if pnls:
        print(f"\n  both-fill rate: {100*len(both)//max(len(both)+len(half),1)}%  (BOTH={len(both)} HALF={len(half)})")
        print(f"  BOTH arb total: ${sum(r['pnl'] for r in both):+.2f} (avg ${sum(r['pnl'] for r in both)/max(len(both),1):+.3f}/cycle)")
        print(f"  HALF total:     ${sum(r['pnl'] for r in half):+.2f} (avg ${sum(r['pnl'] for r in half)/max(len(half),1):+.3f}/cycle)")
        print(f"  median margin (1-bid_sum): {statistics.median([r['margin'] for r in res]):.3f}")
        print(f"  *** NET PnL: ${sum(pnls):+.2f} over {len(pnls)} cycles = {100*sum(pnls)/(SHARES*len(pnls)):+.2f}%/cycle ***")

if __name__=="__main__": main()
