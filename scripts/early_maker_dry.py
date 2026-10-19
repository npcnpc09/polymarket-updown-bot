"""early_maker_dry.py — OBSERVE-ONLY DRY sim of eebde's decoded mechanism: EARLY maker bids on the
underlying-leading side + SCALE-IN, vs our current LATE taker. From window open, at checkpoints
30/60/90/120/150s: read binance lead + PM book for both tokens; on the leading side (|lead|>=THR)
record a maker 'fill' at the current BID (= early cheap price, OPTIMISTIC fill assumption) and add a
unit (scale-in). At settle, resolve (binance) and compare:
  - early_maker: blended bid price across scale-in units on the net-favorite side
  - late_taker:  the ASK of the leading side at 150s (our current style)
GROSS opportunity only (assumes maker fills). Row -> data/early_maker_dry.jsonl
*** NOT a real fill test — maker fills are the unknown (fill-model trap). This bounds the UPSIDE. ***"""
import asyncio, json, time, signal, sys, math, datetime, re
from collections import defaultdict
import httpx
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}
GAMMA="https://gamma-api.polymarket.com/markets"
THR=6.0            # underlying must lead >= this (bps) to commit a unit
ADD_MIN=8.0        # STRICT loading (reverse-engineered): add only while lead toward committed side >= this
RETRACE=3.0        # ... AND not retraced > this from its best-so-far (clean); stop adding on wobble. Reproduces eebde's 96-99% heavy.
CHECKPOINTS=[15,30,45,60,90,120,150,180]   # earlier+more (start ~15s for cheap early fills, like eebde from ~5s)
OUTF="data/early_maker_dry.jsonl"; LOG="data/early_maker_dry.log"
_run=True
def _sig(*_):
    global _run; _run=False
signal.signal(signal.SIGINT,_sig)
def now(): return time.time()
def log(m):
    line=f"[{datetime.datetime.utcnow().strftime('%H:%M:%S')}] {m}"; print(line,flush=True)
    try: open(LOG,"a",encoding="utf-8").write(line+"\n")
    except: pass
async def binance_px(c,sym):
    try:
        r=(await c.get("https://api.binance.com/api/v3/ticker/price",params={"symbol":sym},timeout=8)).json()
        return float(r["price"])
    except: return None
async def tokens(c,slug):
    try:
        arr=(await c.get(GAMMA,params={"slug":slug},timeout=10)).json()
        if arr:
            ids=json.loads(arr[0]["clobTokenIds"]); outs=json.loads(arr[0]["outcomes"])
            return ids[outs.index("Up")], ids[outs.index("Down")]
    except: pass
    return None,None
async def book(c,tok):
    try:
        b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok},timeout=8)).json()
        bids=sorted((float(a["price"]) for a in b.get("bids",[]) if float(a["size"])>0 and 0<float(a["price"])<1),reverse=True)
        asks=sorted(float(a["price"]) for a in b.get("asks",[]) if float(a["size"])>0 and float(a["price"])<1)
        return (bids[0] if bids else None),(asks[0] if asks else None)
    except: return None,None
async def kl_winner(c,sym,st):
    try:
        k1=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":st*1000,"limit":1},timeout=8)).json()
        k2=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":(st+240)*1000,"limit":1},timeout=8)).json()
        o=float(k1[0][1]); cl=float(k2[0][4])
        return "Up" if cl>=o else "Down"
    except: return None
async def main():
    W={}  # slug -> state
    async with httpx.AsyncClient() as c:
        log("early_maker_dry START [OBSERVE-ONLY gross-opportunity sim]")
        while _run:
            t=now(); wstart=int(t//300)*300
            # ensure current window tracked
            for coin,sym in COINS.items():
                slug=f"{coin}-updown-5m-{wstart}"
                if slug not in W:
                    up,dn=await tokens(c,slug)
                    if up:
                        op=await binance_px(c,sym)
                        W[slug]={"coin":coin,"sym":sym,"st":wstart,"up":up,"dn":dn,"open":op,
                                 "units":defaultdict(list),"done_cp":set(),"ask150":None,"side150":None,
                                 "cside":None,"best":-99.0,"still":True}
            # process checkpoints
            for slug,w in list(W.items()):
                sec=t-w["st"]
                if w["open"] is None:
                    w["open"]=await binance_px(c,w["sym"]); continue
                for cp in CHECKPOINTS:
                    if cp in w["done_cp"] or sec<cp or sec>cp+12: continue
                    w["done_cp"].add(cp)
                    px=await binance_px(c,w["sym"])
                    if not px: continue
                    lead=math.log(px/w["open"])*1e4
                    side="Up" if lead>=0 else "Down"
                    # commit to a side at the first checkpoint reaching ADD_MIN
                    if w["cside"] is None and abs(lead)>=ADD_MIN:
                        w["cside"]=side; w["best"]=abs(lead)
                    # STRICT eebde-style loading on the committed side: add only while strong + clean (not retraced); stop on wobble
                    if w["cside"]:
                        ldt=lead if w["cside"]=="Up" else -lead   # lead toward committed side
                        if w["still"] and ldt>=ADD_MIN and ldt>=w["best"]-RETRACE:
                            tok=w["up"] if w["cside"]=="Up" else w["dn"]
                            bid,ask=await book(c,tok)
                            if bid: w["units"][w["cside"]].append(bid)   # early maker fill @ bid (optimistic)
                        elif ldt < w["best"]-RETRACE:
                            w["still"]=False                              # wobble -> stop adding
                        w["best"]=max(w["best"],ldt)
                    # late-taker reference (our current style): ask of leading side at ~150s
                    if cp>=150 and w["ask150"] is None and abs(lead)>=THR:
                        tok2=w["up"] if side=="Up" else w["dn"]
                        _,ask2=await book(c,tok2)
                        w["ask150"]=ask2; w["side150"]=side
                # settle
                if sec>305 and "settled" not in w:
                    w["settled"]=True
                    win=await kl_winner(c,w["sym"],w["st"])
                    if not win: del W[slug]; continue
                    # early maker: net-favorite side = side with most units
                    cnt={s:len(v) for s,v in w["units"].items()}
                    if cnt:
                        fav=max(cnt,key=cnt.get); allpx=[p for v in w["units"].values() for p in v]
                        favpx=w["units"][fav]
                        em_blend=sum(favpx)/len(favpx) if favpx else None
                        em_units=len(favpx)
                        # pnl: each favorite unit pays (1-price) if win else -price; opposite-side units the inverse
                        em_pnl=0.0
                        for s,v in w["units"].items():
                            for p in v: em_pnl += (1-p) if s==win else -p
                        em_win=fav==win
                    else: fav=None; em_blend=None; em_units=0; em_pnl=0.0; em_win=None
                    # late taker (our style): one unit @ ask150 on side150
                    lt_pnl=None; lt_win=None
                    if w["ask150"] and w["side150"]:
                        lt_win=w["side150"]==win
                        lt_pnl=(1-w["ask150"]) if lt_win else -w["ask150"]
                    row={"slug":slug,"coin":w["coin"],"winner":win,"em_fav":fav,"em_units":em_units,
                         "em_blend":round(em_blend,3) if em_blend else None,"em_win":em_win,"em_pnl":round(em_pnl,3),
                         "lt_side":w["side150"],"lt_ask":w["ask150"],"lt_win":lt_win,"lt_pnl":round(lt_pnl,3) if lt_pnl is not None else None}
                    open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
                    log(f"SETTLE {slug} win={win} | early-maker fav={fav} units={em_units} blend={row['em_blend']} pnl={row['em_pnl']:+.2f} | late-taker {w['side150']}@{w['ask150']} pnl={row['lt_pnl']}")
                    del W[slug]
            await asyncio.sleep(6)
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
