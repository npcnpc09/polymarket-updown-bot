"""liquidity_ceiling.py — how much size can the CELL (0.90-0.95) actually absorb? Two reads:
(A) HISTORICAL: our real cell fills — logged adepth (book depth at entry) vs the size we took. If adepth >> our
    size, we have headroom; if ~equal, we're near the limit. Also any partial fills/slippage.
(B) LIVE: probe current btc/eth 5m updown order books, show shares available near 0.85-0.97 (the cell band)."""
import json, httpx, statistics as st
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
# (A) historical cell fills: adepth vs sh
cell=[]
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl",encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None and o.get("B") and 0.90<=o["B"]<0.96:
        cell.append({"sh":o.get("sh"),"adepth":o.get("adepth"),"B":o["B"],"spread":o.get("spread")})
ad=[c["adepth"] for c in cell if c.get("adepth") is not None]
print(f"=== (A) historical cell fills: {len(cell)}, with adepth logged: {len(ad)} ===")
if ad:
    print(f"  book depth at entry (adepth): median={st.median(ad):.0f} mean={st.mean(ad):.0f} p10={sorted(ad)[len(ad)//10]:.0f} p90={sorted(ad)[len(ad)*9//10]:.0f} sh")
    print(f"  our cell size: 20-28sh. headroom vs median depth = {st.median(ad)/28:.1f}x at 28sh")
else:
    print("  no adepth logged on cell fills")
# (B) live book probe
import time
c=httpx.Client(timeout=12,headers={"User-Agent":"x"})
GAMMA="https://gamma-api.polymarket.com/markets"
now=int(time.time()); ws=(now//300)*300
print(f"\n=== (B) LIVE book depth, current btc/eth 5m windows (ws={ws}) ===")
for coin in ("btc","eth"):
    for w in (ws,ws-300):
        slug=f"{coin}-updown-5m-{w}"
        try:
            arr=c.get(GAMMA,params={"slug":slug}).json()
            if not arr: continue
            ids=json.loads(arr[0]["clobTokenIds"]); outs=json.loads(arr[0]["outcomes"])
            for side,tok in zip(outs,ids):
                b=c.get("https://clob.polymarket.com/book",params={"token_id":tok}).json()
                asks=sorted(((float(a["price"]),float(a["size"])) for a in b.get("asks",[]) if 0<float(a["price"])<1),key=lambda x:x[0])
                bids=sorted(((float(a["price"]),float(a["size"])) for a in b.get("bids",[]) if 0<float(a["price"])<1),key=lambda x:-x[0])
                # depth in the cell band 0.88-0.96
                ask_cell=sum(s for p,s in asks if 0.88<=p<=0.96)
                bid_cell=sum(s for p,s in bids if 0.85<=p<=0.95)
                topask=asks[0] if asks else None; topbid=bids[0] if bids else None
                print(f"  {slug} {side}: topbid={topbid} topask={topask} | cell-band asks~{ask_cell:.0f}sh bids~{bid_cell:.0f}sh")
        except Exception as e:
            print(f"  {slug}: {str(e)[:40]}")
        break  # only current window per coin to keep it short
print("\nREAD: scaling headroom = how far our per-trade size can grow before adepth/book depth limits the fill.")
print("If median depth is ~hundreds of sh, 2-4x (to 60-100sh) is feasible; if ~tens, we're near the ceiling.")
print("Remember: maker bid fills on SELL flow, not static depth — eebde scaled via MANY small fills, not big ones.")
