"""passive_maker_observe.py — answer 'can a maker buy the favorite cheaply enough to be +EV?' with REAL
order-book data and ZERO money. Posts NOTHING. For each lead>=MIN window, at checkpoints, snapshot the
lead-side token's mid, then set HYPOTHETICAL resting bids at mid-0/2/4/6c. Track the real best-ask for the
rest of the window: if it ever drops to <= our hypothetical bid, that bid WOULD have filled (price came down
to our level). At settle (binance winner, reliable on favorite side) record per-tier: would-fill? + win?.
Aggregate -> fill% and EV(=win-price) per discount tier = the fill-ratio-vs-discount curve eebde's +8c needs.

CAVEATS (state when reporting): (1) passive = assumes FRONT of queue -> OVERestimates fills (upper bound);
(2) best-ask<=bid is the fill proxy; (3) binance winner. So if even the UPPER-BOUND fill/EV at 4c is bad,
that's a cheap kill. Read-only, no orders. -> data/passive_maker.jsonl"""
import asyncio,json,time,math,os,sys,datetime
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}
GAMMA="https://gamma-api.polymarket.com/markets"
LEAD_MIN=5.0; TIERS=[0.0,0.02,0.04,0.06]   # EARLY-PLACEMENT test v3 2026-06-10: place when lead first appears EARLY (off 15-45s) = front-of-queue (book thin) = passive fill estimate REALISTIC here (vs late placement where real money was back-of-queue 25% vs passive 87%). Tests if early front-of-queue maker escapes adverse selection.  # was: LOOSENED 2026-06-10 10/3->8/2: backtest (600 win) confirmed 8/2 safe (win 87% vs 89%, +22% sample). NOTE: strengthening favorite is FAIRLY priced (win%=price, edge~0); the +EV is purely the MAKER DISCOUNT (fill below ask), real EV ~+0.06/sh at true 89% win, IF fills capture the discount & aren't adverse — that's what this probe tests.
DURS=[("5m",300,[15,30,45],260)]   # EARLY checkpoints only (front of queue, before the trend/crowd builds up)
OUTF=os.path.join(ROOT,"data","passive_maker.jsonl")
def now(): return time.time()
def log(m): print(f"[{datetime.datetime.utcnow().strftime('%H:%M:%S')}] {m}",flush=True)
async def bpx(c,sym):
    try: return float((await c.get("https://api.binance.com/api/v3/ticker/price",params={"symbol":sym},timeout=8)).json()["price"])
    except: return None
async def toks(c,slug):
    try:
        arr=(await c.get(GAMMA,params={"slug":slug},timeout=10)).json()
        if arr:
            ids=json.loads(arr[0]["clobTokenIds"]); outs=json.loads(arr[0]["outcomes"])
            return ids[outs.index("Up")],ids[outs.index("Down")]
    except: pass
    return None,None
async def book(c,tok):
    try:
        b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok},timeout=8)).json()
        bids=sorted((float(a["price"]) for a in b.get("bids",[]) if float(a["size"])>0 and 0<float(a["price"])<1),reverse=True)
        asks=sorted(float(a["price"]) for a in b.get("asks",[]) if float(a["size"])>0 and 0<float(a["price"])<1)
        return (bids[0] if bids else None),(asks[0] if asks else None)
    except: return None,None
async def kwin(c,sym,st,wa=240):
    try:
        k1=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":st*1000,"limit":1},timeout=8)).json()
        k2=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":(st+wa)*1000,"limit":1},timeout=8)).json()
        return "Up" if float(k2[0][4])>=float(k1[0][1]) else "Down"
    except: return None
async def main():
    W={}
    async with httpx.AsyncClient() as c:
        log("passive_maker_observe START — NO orders, real-book fill estimation, tiers mid-0/2/4/6c")
        while True:
            t=now()
            for coin,sym in COINS.items():
                for dn,dsec,cps,wat in DURS:
                    ws=int(t//dsec)*dsec; slug=f"{coin}-updown-{dn}-{ws}"
                    if slug not in W:
                        up,dn2=await toks(c,slug)
                        if up:
                            op=await bpx(c,sym)
                            W[slug]={"coin":coin,"sym":sym,"st":ws,"up":up,"dn":dn2,"open":op,"cps":set(),"leadhist":{},
                                     "probes":[],"cps_list":cps,"wat":wat,"settled":False}
            for slug,w in list(W.items()):
                sec=t-w["st"]
                if w["open"] is None: w["open"]=await bpx(c,w["sym"]); continue
                # new checkpoint probes
                for cp in w["cps_list"]:
                    if cp in w["cps"] or sec<cp or sec>cp+15: continue
                    w["cps"].add(cp)
                    px=await bpx(c,w["sym"])
                    if not px: continue
                    lead=math.log(px/w["open"])*1e4; side="Up" if lead>=0 else "Down"
                    if abs(lead)<LEAD_MIN: continue   # EARLY placement: just a lead present (no strengthening gate -- trend not formed yet this early)
                    tok=w["up"] if side=="Up" else w["dn"]
                    bid,ask=await book(c,tok)
                    if bid is None or ask is None: continue
                    mid=round((bid+ask)/2,3)
                    w["probes"].append({"cp":cp,"side":side,"tok":tok,"mid":mid,"lead":round(lead,1),
                                        "bids":{d:round(mid-d,3) for d in TIERS},"minask":ask})
                    log(f"  probe {slug} {side} cp{cp} lead{lead:+.0f} mid{mid} -> bids {[round(mid-d,2) for d in TIERS]}")
                # update min-ask for active probes (track if price came down to our bid)
                if w["probes"] and not w["settled"]:
                    for tok in set(p["tok"] for p in w["probes"]):
                        _,ask=await book(c,tok)
                        if ask is not None:
                            for p in w["probes"]:
                                if p["tok"]==tok: p["minask"]=min(p["minask"],ask)
                # settle
                if sec>w["wat"]+40 and not w["settled"]:
                    w["settled"]=True
                    win=await kwin(c,w["sym"],w["st"],w["wat"])
                    if win:
                        for p in w["probes"]:
                            won=(p["side"]==win)
                            for d in TIERS:
                                bidp=p["bids"][d]; filled=(p["minask"]<=bidp+1e-9)
                                row={"slug":slug,"coin":w["coin"],"side":p["side"],"win":win,"won":won,"cp":p["cp"],
                                     "lead":p["lead"],"mid":p["mid"],"tier":d,"bid":bidp,"filled":filled,"minask":round(p["minask"],3)}
                                open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
                        log(f"SETTLE {slug} win={win} probes={len(w['probes'])}")
                    del W[slug]
            await asyncio.sleep(5)
import httpx
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
