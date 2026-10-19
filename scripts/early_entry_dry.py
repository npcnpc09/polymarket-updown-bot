"""early_entry_dry.py — A/B DRY sim: EARLY entry (30-60s, the lowbid-probe sweet spot) vs our current
LATE entry (~165s), SAME z>=2.5 gate, SAME real PM book + fill proxy. Per window, on the leading side:
  EARLY: at first checkpoint in [30,45,60]s where z=|lead|/vol>=2.5, post a maker bid at best_bid.
  LATE:  at first checkpoint in [150,165]s where z>=2.5, post a maker bid at best_bid (our style).
A posted bid 'fills' if a later best_bid <= its price (market traded down through it). At settle record
both legs' {price, filled, won}. Compare: does early get cheaper price + higher win + better EV? Forward,
observe-only. -> data/early_entry_dry.jsonl. (fill proxy caveat, like early_lowbid_probe.)"""
import asyncio, json, time, signal, sys, math, datetime, statistics
import httpx
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}
GAMMA="https://gamma-api.polymarket.com/markets"
ZMIN=2.5; EARLY_CP=[30,45,60]; LATE_CP=[150,165]; ALLCP=[30,45,60,90,120,150,165,180,210]
OUTF="data/early_entry_dry.jsonl"; LOG="data/early_entry_dry.log"
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
async def vol30(c,sym):
    try:
        k=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","limit":31},timeout=8)).json()
        cl=[float(x[4]) for x in k]
        return statistics.pstdev([math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))])
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
        log("early_entry_dry START [A/B: 30-60s vs 165s entry, z>=2.5]")
        while _run:
            t=now(); ws=int(t//300)*300
            for coin,sym in COINS.items():
                slug=f"{coin}-updown-5m-{ws}"
                if slug not in W:
                    up,dn=await toks(c,slug)
                    if up:
                        op=await bpx(c,sym); v=await vol30(c,sym)
                        W[slug]={"coin":coin,"sym":sym,"st":ws,"up":up,"dn":dn,"open":op,"vol":v,"done":set(),
                                 "early":None,"late":None}
            for slug,w in list(W.items()):
                sec=t-w["st"]
                if w["open"] is None: w["open"]=await bpx(c,w["sym"]); continue
                if not w["vol"]: w["vol"]=await vol30(c,w["sym"]);
                for cp in ALLCP:
                    if cp in w["done"] or sec<cp or sec>cp+12: continue
                    w["done"].add(cp)
                    px=await bpx(c,w["sym"])
                    if not px or not w["vol"]: continue
                    lead=math.log(px/w["open"])*1e4; side="Up" if lead>=0 else "Down"
                    z=abs(lead)/w["vol"] if w["vol"]>0 else 0
                    # commit EARLY (first 30-60s checkpoint with z>=2.5)
                    if w["early"] is None and cp in EARLY_CP and z>=ZMIN:
                        tok=w["up"] if side=="Up" else w["dn"]; bid=await topbid(c,tok)
                        if bid: w["early"]={"side":side,"p":round(bid,2),"tok":tok,"filled":False,"cp":cp,"z":round(z,2)}
                    # commit LATE (first 150-165s checkpoint with z>=2.5)
                    if w["late"] is None and cp in LATE_CP and z>=ZMIN:
                        tok=w["up"] if side=="Up" else w["dn"]; bid=await topbid(c,tok)
                        if bid: w["late"]={"side":side,"p":round(bid,2),"tok":tok,"filled":False,"cp":cp,"z":round(z,2)}
                    # fill checks
                    for leg in (w["early"],w["late"]):
                        if leg and not leg["filled"]:
                            bb=await topbid(c,leg["tok"])
                            if bb is not None and bb<=leg["p"]: leg["filled"]=True
                if sec>305 and "settled" not in w:
                    w["settled"]=True
                    if w["early"] or w["late"]:
                        win=await kwin(c,w["sym"],w["st"])
                        if win:
                            def leginfo(leg):
                                if not leg: return None
                                return {"side":leg["side"],"price":leg["p"],"filled":leg["filled"],"cp":leg["cp"],"z":leg["z"],"won":leg["side"]==win}
                            row={"slug":slug,"coin":w["coin"],"winner":win,"early":leginfo(w["early"]),"late":leginfo(w["late"])}
                            open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
                            e=row["early"]; la=row["late"]
                            log(f"SETTLE {slug} win={win} | EARLY {e['cp'] if e else '-'}s @{e['price'] if e else '-'} fill={e['filled'] if e else '-'} won={e['won'] if e else '-'} | LATE @{la['price'] if la else '-'} won={la['won'] if la else '-'}")
                    del W[slug]
            await asyncio.sleep(5)
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
