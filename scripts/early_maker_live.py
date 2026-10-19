"""early_maker_live.py — REAL-money test of eebde's mechanism: EARLY post_only MAKER bids on the
underlying-leading side (lead confirmed >= LEAD_MIN), scale-in, hold to settle. The ONLY honest way to
answer 'can WE capture the cheap maker fills, or do we get adversely selected?' — paper probes assume
fills (the trap). This posts REAL resting bids and measures the ACTUAL fill ratio (winners vs losers).

  DRY  (default): post NO orders, just log what it WOULD post (sanity).
  --place        : REAL post_only BUY bids, tiny. HARD CAPS below. Wallet 0x149200 COMPROMISED -> tiny.
Agent-initiated real orders are permission-gated; USER must authorize. NOT in watchdog. -> data/early_maker_live.jsonl"""
import asyncio, json, time, signal, sys, os, math, datetime, re
from collections import defaultdict
import httpx
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACE=("--place" in sys.argv)
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}
GAMMA="https://gamma-api.polymarket.com/markets"
LEAD_MIN=5.0; CHECKPOINTS=[30,60,90,120]; SHARES=5
# (name, window_secs, checkpoints, settle_after, win_eval_offset). 15m: checkpoints scaled ~x3, settle +908, win = open vs +840s(14min)
DURS=[("5m",300,[30,60,90,120],308,240),("15m",900,[90,180,270,360],908,840)]
MAX_CONCURRENT=3; MAX_PER_COIN=2; MAX_TOTAL_ORDERS=200; STOP_LOSS=-15.0; BID_OFFSET=0.0; PRICE_CAP=0.85  # PRICE_CAP added 2026-06-09: skip >=0.85 (blind -7.5%, thin-win/fat-loss overpriced favorite zone)
OUTF=os.path.join(ROOT,"data","early_maker_live.jsonl"); LOG=os.path.join(ROOT,"data","early_maker_live.log")
_run=True
def _sig(*_):
    global _run; _run=False
signal.signal(signal.SIGINT,_sig)
def now(): return time.time()
def log(m):
    line=f"[{datetime.datetime.utcnow().strftime('%H:%M:%S')}] {m}"; print(line,flush=True)
    try: open(LOG,"a",encoding="utf-8").write(line+"\n")
    except: pass
def load_env():
    for l in open(os.path.join(ROOT,".env"),encoding="utf-8"):
        if "=" in l and not l.startswith("#"):
            k,v=l.strip().split("=",1); os.environ.setdefault(k.strip(),v.strip())
    return os.environ["POLY_PK"],os.environ["POLY_PROXY"]
def trader():
    pk,proxy=load_env(); from polymarket import SecureClient
    return SecureClient.create(private_key=pk,wallet=proxy)
async def bpx(c,sym):
    try:
        r=(await c.get("https://api.binance.com/api/v3/ticker/price",params={"symbol":sym},timeout=8)).json(); return float(r["price"])
    except: return None
_volcache={"t":0.0,"v":None}
async def btc_vol30(c):
    """BTC realized vol (stdev of 1-min log returns, bps/min) over last 30 min. Cached 60s. LABEL ONLY
    for regime forward-validation — does maker EV drop in high BTC vol (the week-backtest -0.327 signal)?"""
    if time.time()-_volcache["t"]<60 and _volcache["v"] is not None: return _volcache["v"]
    try:
        k=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":"BTCUSDT","interval":"1m","limit":31},timeout=8)).json()
        cl=[float(x[4]) for x in k]
        rets=[math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))]
        m=sum(rets)/len(rets); v=(sum((x-m)**2 for x in rets)/len(rets))**0.5
        _volcache["t"]=time.time(); _volcache["v"]=round(v,2); return _volcache["v"]
    except: return None
async def toks(c,slug):
    try:
        arr=(await c.get(GAMMA,params={"slug":slug},timeout=10)).json()
        if arr:
            ids=json.loads(arr[0]["clobTokenIds"]); outs=json.loads(arr[0]["outcomes"])
            return ids[outs.index("Up")],ids[outs.index("Down")]
    except: pass
    return None,None
async def topbid(c,tok):
    try:
        b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok},timeout=8)).json()
        bids=sorted((float(a["price"]) for a in b.get("bids",[]) if float(a["size"])>0 and 0<float(a["price"])<1),reverse=True)
        return bids[0] if bids else None
    except: return None
async def kwin(c,sym,st,wa=240):
    try:
        k1=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":st*1000,"limit":1},timeout=8)).json()
        k2=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":(st+wa)*1000,"limit":1},timeout=8)).json()
        return "Up" if float(k2[0][4])>=float(k1[0][1]) else "Down"
    except: return None
async def main():
    cli=None; realized=0.0; orders=0; halted=False
    W={}
    if PLACE:
        cli=trader()
        try: bal=float(cli.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6; log(f"LIVE wallet ${bal:.2f}")
        except Exception as e: log(f"bal err {str(e)[:50]}")
    async with httpx.AsyncClient() as c:
        log(f"early_maker_live START [{'LIVE --place caps:%dsh/conc%d/stop$%g' %(SHARES,MAX_CONCURRENT,STOP_LOSS) if PLACE else 'DRY'}] post maker bid on lead>=%g side"%LEAD_MIN)
        while _run:
            t=now()
            for coin,sym in COINS.items():
                for dname,dsec,cps,settle_at,win_at in DURS:
                    ws=int(t//dsec)*dsec
                    slug=f"{coin}-updown-{dname}-{ws}"
                    if slug not in W:
                        up,dn=await toks(c,slug)
                        if up:
                            op=await bpx(c,sym)
                            W[slug]={"coin":coin,"sym":sym,"st":ws,"up":up,"dn":dn,"open":op,"orders":[],"cps":set(),"settled":False,
                                     "cps_list":cps,"settle_at":settle_at,"win_at":win_at}
            for slug,w in list(W.items()):
                sec=t-w["st"]
                if w["open"] is None: w["open"]=await bpx(c,w["sym"]); continue
                for cp in w["cps_list"]:
                    if cp in w["cps"] or sec<cp or sec>cp+15: continue
                    w["cps"].add(cp)
                    px=await bpx(c,w["sym"])
                    if not px: continue
                    lead=math.log(px/w["open"])*1e4; side="Up" if lead>=0 else "Down"
                    toward=abs(lead)
                    if toward<LEAD_MIN: continue
                    tok=w["up"] if side=="Up" else w["dn"]
                    bid=await topbid(c,tok)
                    if not bid: continue
                    price=round(min(bid+BID_OFFSET,0.97),2)
                    if price>=PRICE_CAP:  # skip overpriced favorite zone
                        log(f"  skip {slug} {side} @ {price} >= cap {PRICE_CAP}"); continue
                    coin_open=sum(1 for o in w["orders"] if not o.get("done"))
                    if PLACE:
                        if halted or orders>=MAX_TOTAL_ORDERS or realized<=STOP_LOSS:
                            if realized<=STOP_LOSS and not halted: log("=== STOP-LOSS HALT ==="); halted=True
                            continue
                        liveN=sum(len([o for o in ww["orders"] if not o.get("done")]) for ww in W.values())
                        if liveN>=MAX_CONCURRENT: continue
                        try:
                            r=cli.place_limit_order(token_id=tok,price=price,size=SHARES,side="BUY",post_only=True)
                            oid=getattr(r,"order_id",None) or getattr(r,"id",None)
                        except Exception as ex: log(f"  place-blocked/err {slug}: {str(ex)[:80]}"); continue
                        if not oid: continue
                        w["orders"].append({"side":side,"price":price,"oid":oid,"filled":False,"cp":cp}); orders+=1
                        log(f"*** MAKER-BID #{orders} {slug} {side} {SHARES}sh @ {price} (lead{lead:+.0f}) oid={str(oid)[:10]} ***")
                    else:
                        w["orders"].append({"side":side,"price":price,"oid":None,"filled":True,"cp":cp})  # DRY assume fill
                        log(f"[DRY] would post {slug} {side} @ {price} (lead{lead:+.0f})")
                # poll fills (PLACE)
                if PLACE and cli:
                    for o in w["orders"]:
                        if o["filled"] or o.get("done"): continue
                        try:
                            od=cli.get_order(order_id=o["oid"]); mt=float(getattr(od,"size_matched",0) or 0)
                            if mt>=SHARES-1e-6: o["filled"]=True; log(f"  *** FILLED {slug} {o['side']} @ {o['price']} ***")
                        except: pass
                # settle
                if sec>w["settle_at"] and not w["settled"]:
                    w["settled"]=True
                    win=await kwin(c,w["sym"],w["st"],w["win_at"])
                    if PLACE and cli:
                        for o in w["orders"]:
                            if not o["filled"]:
                                try: cli.cancel_order(order_id=o["oid"])
                                except: pass
                                o["done"]=True
                    filled=[o for o in w["orders"] if o["filled"]]
                    if filled and win:
                        nW=sum(1 for o in filled if o["side"]==win); nL=len(filled)-nW
                        pnl=sum(((1-o["price"]) if o["side"]==win else -o["price"]) for o in filled)*SHARES
                        if PLACE: realized+=pnl
                        bv=await btc_vol30(c)
                        row={"slug":slug,"coin":w["coin"],"winner":win,"n_filled":len(filled),"n_W":nW,"n_L":nL,
                             "avg_px":round(sum(o["price"] for o in filled)/len(filled),3),"pnl":round(pnl,2),"live":PLACE,"btc_vol":bv}
                        open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
                        log(f"SETTLE {slug} win={win} filled={len(filled)} (W{nW}/L{nL}) avg@{row['avg_px']} pnl=${pnl:+.2f}{' cum$%+.2f'%realized if PLACE else ''}")
                    del W[slug]
            await asyncio.sleep(5)
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
