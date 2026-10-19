"""early_lowbid_probe.py — DRY probe: how LOW can we push the maker entry price toward eebde's 0.67?
At the first early checkpoint where the underlying leads (>=THR), on the leading side, post hypothetical
RESTING BIDS at several discount levels below the best bid (0/2/4/6 ticks). At later checkpoints, read the
real PM book: a posted bid at price P is 'FILLED' if the best bid later drops to <= P (the market traded
down through our level). At settle, record per offset: filled?, fill price, and the committed side's win.
Aggregate -> fill RATE vs avg PRICE vs WIN-rate(adverse selection) per discount level = the price-vs-fill
tradeoff that says how close to eebde's 0.67 we can realistically get. OBSERVE-ONLY (no orders).
*** Fill proxy = best_bid<=P later; real fills need trade flow, but this bounds achievability. ***"""
import asyncio, json, time, signal, sys, math, datetime
import httpx
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}
GAMMA="https://gamma-api.polymarket.com/markets"
THR=6.0; OFFSETS=[0.0,0.02,0.04,0.06]; CHECKPOINTS=[15,30,45,60,90,120,150,180,210]
OUTF="data/early_lowbid_probe.jsonl"; LOG="data/early_lowbid_probe.log"
_run=True
def _sig(*_):
    global _run; _run=False
signal.signal(signal.SIGINT,_sig)
def now(): return time.time()
def log(m):
    line=f"[{datetime.datetime.utcnow().strftime('%H:%M:%S')}] {m}"; print(line,flush=True)
    try: open(LOG,"a",encoding="utf-8").write(line+"\n")
    except: pass
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
async def topbid(c,tok):
    try:
        b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok},timeout=8)).json()
        bids=sorted((float(a["price"]) for a in b.get("bids",[]) if float(a["size"])>0 and 0<float(a["price"])<1),reverse=True)
        return bids[0] if bids else None
    except: return None
async def kwin(c,sym,st):
    try:
        k1=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":st*1000,"limit":1},timeout=8)).json()
        k2=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":(st+240)*1000,"limit":1},timeout=8)).json()
        return "Up" if float(k2[0][4])>=float(k1[0][1]) else "Down"
    except: return None
async def main():
    W={}
    async with httpx.AsyncClient() as c:
        log("early_lowbid_probe START [observe: how low can maker entry go]")
        while _run:
            t=now(); ws=int(t//300)*300
            for coin,sym in COINS.items():
                slug=f"{coin}-updown-5m-{ws}"
                if slug not in W:
                    up,dn=await toks(c,slug)
                    if up:
                        op=await bpx(c,sym)
                        W[slug]={"coin":coin,"sym":sym,"st":ws,"up":up,"dn":dn,"open":op,"done":set(),
                                 "cside":None,"tok":None,"posts":None}
            for slug,w in list(W.items()):
                sec=t-w["st"]
                if w["open"] is None: w["open"]=await bpx(c,w["sym"]); continue
                for cp in CHECKPOINTS:
                    if cp in w["done"] or sec<cp or sec>cp+12: continue
                    w["done"].add(cp)
                    px=await bpx(c,w["sym"])
                    if not px: continue
                    lead=math.log(px/w["open"])*1e4; side="Up" if lead>=0 else "Down"
                    # commit at first checkpoint with a real lead; post bids at offsets below best bid
                    if w["cside"] is None and abs(lead)>=THR:
                        tok=w["up"] if side=="Up" else w["dn"]
                        bid=await topbid(c,tok)
                        if bid:
                            w["cside"]=side; w["tok"]=tok; w["commit_bid"]=bid; w["commit_sec"]=round(sec)
                            w["posts"]={off:{"p":round(max(0.02,bid-off),2),"filled":False} for off in OFFSETS}
                    # check fills: a resting bid at P fills if best bid later drops to <= P
                    if w["posts"]:
                        bid=await topbid(c,w["tok"])
                        if bid is not None:
                            for off,d in w["posts"].items():
                                if not d["filled"] and bid<=d["p"]: d["filled"]=True
                if sec>305 and "settled" not in w:
                    w["settled"]=True
                    if w["posts"]:
                        win=await kwin(c,w["sym"],w["st"])
                        if win:
                            won=(w["cside"]==win)
                            row={"slug":slug,"coin":w["coin"],"side":w["cside"],"won":won,
                                 "commit_sec":w.get("commit_sec"),"commit_bid":w.get("commit_bid"),
                                 "fills":{str(off):{"price":d["p"],"filled":d["filled"]} for off,d in w["posts"].items()}}
                            open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
                            f=[o for o,d in w["posts"].items() if d["filled"]]
                            log(f"SETTLE {slug} {w['cside']} won={won} commitBid={w.get('commit_bid')} filled-offsets={f}")
                    del W[slug]
            await asyncio.sleep(6)
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
