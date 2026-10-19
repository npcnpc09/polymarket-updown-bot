"""cont_avg_bot.py — eebde replication: continuous-averaging into STRENGTHENING favorites. Per btc/eth 5m
window:
  1. BASE: when |binance lead| first >= LEAD_BASE early (off OFF_BASE), taker-buy BASE_SH on the lead side
     (cheap early entry). Record lead_base, peak.
  2. ADDS: at checkpoints, if the lead toward our side is STILL STRENGTHENING (>= lead_base AND >= LEAD_ADD)
     and clean (not retraced > RETRACE from its peak), taker-ADD ADD_SH (value-weight the persisters).
  3. WOBBLE: if lead retraces > RETRACE from peak, STOP adding (don't load faders).
  4. Hold to settle. Diversify across windows. Real PnL = wallet/redeem (binance log is a label).
Validated mechanism (real settlement): strengtheners win 94-95%, heavy=persisters=97%; the averaging marries
cheap-early-base (0.67) + heavy-add-on-strengthener (95%) = eebde's +18.8%. DRY default; --place = real.
HARD CAPS below. Run after injecting ~$300-500."""
import asyncio, json, time, signal, sys, os, math, datetime
import httpx
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACE=("--place" in sys.argv)
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}; GAMMA="https://gamma-api.polymarket.com/markets"
LEAD_BASE=5.0; OFF_BASE=(15,70)        # early cheap base when lead first crosses 5
ADD_CHECKS=[90,150,210]; LEAD_ADD=8.0  # add at these offsets if still strengthening & >=8
RETRACE=3.0                            # if lead retraced >3 from peak -> wobble, stop adding
BASE_SH=150; ADD_SH=200; MAX_ADDS=3    # $5000-SCALE DRY sim 2026-06-10: base 150 + up to 3x200 = ~750sh/heavy window (~$560), value-weight persisters
PRICE_CAP=0.92                         # don't buy above this (no edge left)
MAX_CONCURRENT=10; MAX_TOTAL_ORDERS=300; STOP_LOSS=-1500.0  # scaled for $5000 sim (DRY=paper, stop moot)
OUTF=os.path.join(ROOT,"data","cont_avg_bot.jsonl"); LOG=os.path.join(ROOT,"data","cont_avg_bot.log")
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
    try: return float((await c.get("https://api.binance.com/api/v3/ticker/price",params={"symbol":sym},timeout=8)).json()["price"])
    except: return None
async def kopen(c,sym,st):
    try: return float((await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":st*1000,"limit":1},timeout=8)).json()[0][1])
    except: return None
async def toks(c,slug):
    try:
        a=(await c.get(GAMMA,params={"slug":slug},timeout=10)).json()
        if a: ids=json.loads(a[0]["clobTokenIds"]); outs=json.loads(a[0]["outcomes"]); return ids[outs.index("Up")],ids[outs.index("Down")]
    except: pass
    return None,None
async def topask(c,tok):
    try:
        b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok},timeout=8)).json()
        asks=sorted(float(a["price"]) for a in b.get("asks",[]) if float(a["size"])>0 and 0<float(a["price"])<1)
        return asks[0] if asks else None
    except: return None
async def our_fill(c,proxy,slug,side):
    try:
        a=(await c.get("https://data-api.polymarket.com/activity",params={"user":proxy,"limit":60},timeout=10)).json()
        f=[(x.get("price"),x.get("size") or 0) for x in a if isinstance(x,dict) and x.get("type")=="TRADE" and (x.get("side") or "").upper()=="BUY" and x.get("slug")==slug and x.get("outcome")==side and x.get("price")]
        tot=sum(s for _,s in f)
        if tot>0: return sum(p*s for p,s in f)/tot
    except: pass
    return None
async def kwin(c,sym,st,wa=240):
    try:
        k1=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":st*1000,"limit":1},timeout=8)).json()
        k2=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":(st+wa)*1000,"limit":1},timeout=8)).json()
        return "Up" if float(k2[0][4])>=float(k1[0][1]) else "Down"
    except: return None
async def buy(cli,c,proxy,tok,slug,side,sh):
    """taker buy sh shares; return real avg fill price (or None)."""
    ask=await topask(c,tok)
    if not ask or ask>=PRICE_CAP: return None,ask
    try:
        r=cli.place_limit_order(token_id=tok,price=round(min(ask+0.01,0.97),2),size=sh,side="BUY",post_only=False)
        if not (getattr(r,"order_id",None) or getattr(r,"id",None)): return None,ask
    except Exception as ex: log(f"  buy err {slug}:{str(ex)[:60]}"); return None,ask
    await asyncio.sleep(1.0)
    rp=await our_fill(c,proxy,slug,side)
    return (rp or round(min(ask+0.01,0.97),2)),ask
async def main():
    cli=None; proxy=None; realized=0.0; orders=0; halted=False; W={}
    if PLACE:
        cli=trader(); proxy=os.environ.get("POLY_PROXY")
        try: log(f"LIVE wallet ${float(cli.get_balance_allowance(asset_type='COLLATERAL').balance)/1e6:.2f}")
        except Exception as e: log(f"bal err {str(e)[:40]}")
    async with httpx.AsyncClient() as c:
        log(f"cont_avg_bot START [{'LIVE base%d+add%dx%d/conc%d/stop$%g'%(BASE_SH,ADD_SH,MAX_ADDS,MAX_CONCURRENT,STOP_LOSS) if PLACE else 'DRY'}] base@lead>={LEAD_BASE} early, add on strengthening")
        while _run:
            t=now()
            for coin,sym in COINS.items():
                ws=int(t//300)*300; slug=f"{coin}-updown-5m-{ws}"
                if slug not in W:
                    up,dn=await toks(c,slug)
                    if up: W[slug]={"coin":coin,"sym":sym,"st":ws,"up":up,"dn":dn,"open":await kopen(c,sym,ws),"side":None,"lead_base":None,"peak":None,"fills":[],"adds":set(),"wobble":False,"settled":False}
            for slug,w in list(W.items()):
                sec=t-w["st"]
                if w["open"] is None: w["open"]=await kopen(c,w["sym"],w["st"]); continue
                px=await bpx(c,w["sym"]) if (sec<=max(ADD_CHECKS)+10 and not w["settled"]) else None
                lead=math.log(px/w["open"])*1e4 if px else None
                halt_new = PLACE and (halted or orders>=MAX_TOTAL_ORDERS or realized<=STOP_LOSS)
                if PLACE and realized<=STOP_LOSS and not halted: log("=== STOP-LOSS HALT ==="); halted=True
                concN=sum(1 for ww in W.values() if ww["fills"] and not ww.get("settled"))
                # BASE
                if w["side"] is None and lead is not None and OFF_BASE[0]<=sec<=OFF_BASE[1] and abs(lead)>=LEAD_BASE:
                    if not halt_new and concN<MAX_CONCURRENT:
                        side="Up" if lead>=0 else "Down"; tok=w["up"] if side=="Up" else w["dn"]
                        if PLACE:
                            paid,ask=await buy(cli,c,proxy,tok,slug,side,BASE_SH)
                            if paid: orders+=1; w["fills"].append((paid,BASE_SH)); w["side"]=side; w["lead_base"]=abs(lead); w["peak"]=abs(lead)
                            log(f"*** BASE #{orders} {slug} {side} {BASE_SH}sh @{paid if paid else 'noFill'} (lead{lead:+.0f}@{sec:.0f}s)")
                        else:
                            ask=await topask(c,tok)
                            if ask and ask<PRICE_CAP: w["fills"].append((ask,BASE_SH)); w["side"]=side; w["lead_base"]=abs(lead); w["peak"]=abs(lead); log(f"[DRY] BASE {slug} {side} @{ask:.3f} (lead{lead:+.0f}@{sec:.0f}s)")
                # ADDS on strengthening
                elif w["side"] and lead is not None and not w["wobble"] and len(w["adds"])<MAX_ADDS:
                    lt=lead*(1 if w["side"]=="Up" else -1)  # lead toward our side
                    if lt>w["peak"]: w["peak"]=lt
                    if w["peak"]-lt>RETRACE: w["wobble"]=True; log(f"  WOBBLE {slug} lead retraced {w['peak']-lt:.0f} -> stop adding")
                    else:
                        for ck in ADD_CHECKS:
                            if ck in w["adds"] or sec<ck or sec>ck+15: continue
                            if lt>=LEAD_ADD and lt>=w["lead_base"]:  # still strengthening
                                w["adds"].add(ck); tok=w["up"] if w["side"]=="Up" else w["dn"]
                                if not halt_new:
                                    if PLACE:
                                        paid,ask=await buy(cli,c,proxy,tok,slug,w["side"],ADD_SH)
                                        if paid: orders+=1; w["fills"].append((paid,ADD_SH)); log(f"  ADD #{orders} {slug} {w['side']} {ADD_SH}sh @{paid} (lt{lt:+.0f}@{sec:.0f}s)")
                                    else:
                                        ask=await topask(c,tok)
                                        if ask and ask<PRICE_CAP: w["fills"].append((ask,ADD_SH)); log(f"[DRY] ADD {slug} {w['side']} @{ask:.3f} (lt{lt:+.0f}@{sec:.0f}s)")
                            break
                # SETTLE
                if sec>308 and not w["settled"]:
                    w["settled"]=True
                    if w["fills"]:
                        win=await kwin(c,w["sym"],w["st"]); won=(w["side"]==win) if win else None
                        sh=sum(s for _,s in w["fills"]); cost=sum(p*s for p,s in w["fills"]); avg=cost/sh if sh else 0
                        pnl=((sh-cost) if won else -cost) if won is not None else 0.0
                        if PLACE and won is not None: realized+=pnl
                        row={"slug":slug,"coin":w["coin"],"side":w["side"],"won":won,"n_fills":len(w["fills"]),"shares":sh,"avg_px":round(avg,3),"pnl":round(pnl,2),"lead_base":w["lead_base"],"peak":round(w["peak"] or 0,1),"wobble":w["wobble"],"live":PLACE}
                        open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
                        log(f"SETTLE {slug} {w['side']} {len(w['fills'])}买 {sh}sh avg@{avg:.3f} {'WON' if won else 'LOST'} ${pnl:+.2f}{' cum$%+.2f'%realized if PLACE else ''}")
                    del W[slug]
            await asyncio.sleep(4)
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
