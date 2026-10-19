"""passive_twosided.py v2 — TWO-SIDED MAKER test + CHOP PREDICTOR. Zero money, real order book. v1 showed
two-sided maker is regime-dependent (chop +EV, trend −EV via adverse selection). v2 adds an EX-ANTE chop
predictor computed at entry (~45s) from the binance lead path SO FAR, to test: can we predict chop and thus
run two-sided ONLY in predicted-chop windows (=+EV)? Predictors (first ENTRY_HI s of the window):
  chop_score = (lead range so far) / max(|current lead|,1)   # big swing, small net dir = choppy
  flips      = # times the lead crossed 0 (price crossed open) # more crossings = choppier
Per 5m window: snapshot mid_Up/mid_Down + chop metrics at entry, rest hypo bids mid-0/2/4/6c each side, track
each token real min-ask = would-fill, settle by binance winner. Row records fills + PnL + chop_score + flips.
analyze_twosided.py buckets by predictor: if predicted-chop windows are +EV and predicted-trend −EV, the
conditional 'two-sided only when chop predicted' is +EV. -> data/twosided.jsonl (fresh; v1 rows lack chop_*)."""
import asyncio,json,time,math,os,sys,datetime
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}; GAMMA="https://gamma-api.polymarket.com/markets"
TIERS=[0.0,0.02,0.04,0.06]; ENTRY_LO=40; ENTRY_HI=70; WIN_AT=240; SETTLE=300
OUTF=os.path.join(ROOT,"data","twosided.jsonl")
def now(): return time.time()
def log(m): print(f"[{datetime.datetime.utcnow().strftime('%H:%M:%S')}] {m}",flush=True)
async def toks(c,slug):
    try:
        a=(await c.get(GAMMA,params={"slug":slug},timeout=10)).json()
        if a: ids=json.loads(a[0]["clobTokenIds"]); outs=json.loads(a[0]["outcomes"]); return ids[outs.index("Up")],ids[outs.index("Down")]
    except: pass
    return None,None
async def book(c,tok):
    try:
        b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok},timeout=8)).json()
        bids=sorted((float(a["price"]) for a in b.get("bids",[]) if float(a["size"])>0 and 0<float(a["price"])<1),reverse=True)
        asks=sorted(float(a["price"]) for a in b.get("asks",[]) if float(a["size"])>0 and 0<float(a["price"])<1)
        return (bids[0] if bids else None),(asks[0] if asks else None)
    except: return None,None
async def chop(c,sym,st,upto):
    """ex-ante chop metrics from binance 1s lead path over [st, st+upto]: (chop_score, flips, curlead)"""
    try:
        k=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1s","startTime":st*1000,"endTime":(st+upto)*1000,"limit":200},timeout=8)).json()
        if not isinstance(k,list) or len(k)<15: return None
        op=float(k[0][1]); leads=[math.log(float(x[4])/op)*1e4 for x in k]
        rng=max(leads)-min(leads); cur=leads[-1]
        flips=sum(1 for i in range(1,len(leads)) if (leads[i]>0)!=(leads[i-1]>0) and abs(leads[i])>1)
        return round(rng/max(abs(cur),1.0),2),flips,round(cur,1)
    except: return None
async def kwin(c,sym,st,wa=240):
    try:
        k1=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":st*1000,"limit":1},timeout=8)).json()
        k2=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":(st+wa)*1000,"limit":1},timeout=8)).json()
        return "Up" if float(k2[0][4])>=float(k1[0][1]) else "Down"
    except: return None
async def main():
    W={}
    async with httpx.AsyncClient() as c:
        log("passive_twosided v2 START — two-sided maker + chop predictor (chop_score, flips), NO orders")
        while True:
            t=now()
            for coin,sym in COINS.items():
                ws=int(t//SETTLE)*SETTLE; slug=f"{coin}-updown-5m-{ws}"
                if slug not in W:
                    up,dn=await toks(c,slug)
                    if up: W[slug]={"coin":coin,"sym":sym,"st":ws,"up":up,"dn":dn,"snap":False,"settled":False,
                                    "midU":None,"midD":None,"minaU":9,"minaD":9,"cs":None,"flips":None,"cl":None}
            for slug,w in list(W.items()):
                sec=t-w["st"]
                if not w["snap"] and ENTRY_LO<=sec<=ENTRY_HI:
                    bU,aU=await book(c,w["up"]); bD,aD=await book(c,w["dn"]); cm=await chop(c,w["sym"],w["st"],int(sec))
                    if bU and aU and bD and aD and cm:
                        w["midU"]=round((bU+aU)/2,3); w["midD"]=round((bD+aD)/2,3); w["cs"],w["flips"],w["cl"]=cm; w["snap"]=True
                        log(f"  snap {slug} midU{w['midU']} midD{w['midD']} chop_score{w['cs']} flips{w['flips']} lead{w['cl']} @{sec:.0f}s")
                if w["snap"] and not w["settled"]:
                    _,aU=await book(c,w["up"]); _,aD=await book(c,w["dn"])
                    if aU: w["minaU"]=min(w["minaU"],aU)
                    if aD: w["minaD"]=min(w["minaD"],aD)
                if w["snap"] and not w["settled"] and sec>SETTLE+30:
                    w["settled"]=True; win=await kwin(c,w["sym"],w["st"],WIN_AT)
                    if win:
                        for d in TIERS:
                            bidU=round(w["midU"]-d,3); bidD=round(w["midD"]-d,3)
                            fU=w["minaU"]<=bidU+1e-9; fD=w["minaD"]<=bidD+1e-9; pnl=0.0
                            if fU: pnl+=(1-bidU) if win=="Up" else -bidU
                            if fD: pnl+=(1-bidD) if win=="Down" else -bidD
                            row={"slug":slug,"coin":w["coin"],"win":win,"tier":d,"midU":w["midU"],"midD":w["midD"],
                                 "bidU":bidU,"bidD":bidD,"fillU":fU,"fillD":fD,"both":fU and fD,
                                 "cost":round((bidU if fU else 0)+(bidD if fD else 0),3),"pnl":round(pnl,3),
                                 "chop_score":w["cs"],"flips":w["flips"],"entry_lead":w["cl"]}
                            open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
                        log(f"SETTLE {slug} win={win} chop_score{w['cs']} flips{w['flips']} both?{w['minaU']<=w['midU']-0.04 and w['minaD']<=w['midD']-0.04}")
                    del W[slug]
            await asyncio.sleep(5)
import httpx
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
