"""early_taker_probe.py — the LAST piece: can we capture the +13-24% ROI cell (lead>=8 while price<0.85)
that real_taker_backtest.py proved exists? It's an EXECUTION question now, not EV. This watches the binance
lead and, the moment |lead| FIRST crosses LEAD_TRIG early in a window, reads the REAL ask (the taker price
we'd actually pay) on the lead side and records it + offset + outcome.

  DRY (default): reads the REAL ask but places NO order -> measures the achievable taker price at ZERO risk
                 (the key execution question: when lead crosses 8 early, is the ask still <0.85?).
  --place      : REAL taker buy (marketable limit at the ask), tiny. HARD CAPS. Wallet COMPROMISED -> tiny.
Agent-initiated real orders are permission-gated; USER must authorize. NOT in watchdog. -> data/early_taker_probe.jsonl"""
import asyncio, json, time, signal, sys, os, math, datetime
import httpx
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACE=("--place" in sys.argv)
def _argval(flag,default=None):
    if flag in sys.argv:
        i=sys.argv.index(flag)
        if i+1<len(sys.argv): return sys.argv[i+1]
    return default
# --coins lets a SEPARATE instance run a different coin set (e.g. SOL probe) without touching the
# btc/eth instance. Default = btc,eth (unchanged). --tag suffixes the output/log files so instances
# don't share files. --stop / --maxconc override caps for a conservative experimental probe.
_ALL_SYMS={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT","xrp":"XRPUSDT","doge":"DOGEUSDT","bnb":"BNBUSDT"}
_coins_arg=_argval("--coins","btc,eth")
COINS={c:_ALL_SYMS[c] for c in _coins_arg.split(",") if c in _ALL_SYMS}
_TAG=_argval("--tag","")
GAMMA="https://gamma-api.polymarket.com/markets"
LEAD_TRIG=8.0          # |binance lead| crossing this = a CROSS candidate (the +EV threshold from backtest)
CONFIRM_SEC=15         # 'early but accurate': after a cross, wait this long; enter ONLY if lead still >=8 same
                       # side (backtest: lifts win 73%->85%; the faded crosses = spikes win only ~48%)
PRICE_CAP=0.90         # RAISED 2026-06-11 0.85->0.90: priced_in skip-tracking showed 0.85-0.90 is +EV with our selection — strict band vol<6.5 n=27 would-win 92.6% edge +5.3%, plus n=56 ask-rose-into-band +$11.50; all-trader real fills (06-07/08) band edge +9.5% 2/2 days (btc-driven; eth ~breakeven there = watch item). Worst observed day -1.6% ~ noise. >=0.90 stays banned (tracked -EV: 81.2% would-win vs 92.2% needed). REVERT RULE: live band fills cum < -$8 -> back to 0.85. (Prior history: 0.70->0.85 2026-06-09, the <0.70 split was 30-trade noise.)
MAX_OFFSET=180         # only catch EARLY (cross must be <=180s into a 5m window); later = priced-in
FLIP_CAP=1.01          # DISABLED 2026-06-11 (user rule: NO new filter without independent backtest — the 0.51 gate
                       # was deployed off in-sample live-fill mining, reverted ~01:00 same day pending backtest on
                       # all-trader real fills + week reconstruction. flip60 still computed & logged on every row
                       # (instrumentation is free). If backtest confirms, re-enable at the validated threshold.
                       # In-sample signal that motivated it: vol<6.5 taker calm-flip 89.5%/+$20.75 vs high-flip 70.8%/−$9.15.
VOL_CAP=float(_argval("--volcap","6.5"))   # default 6.5 (BTC). SOL instance: --volcap 10.0 (see VOL_SYM note).
BREAKER_K=int(_argval("--breakerk","3"))    # combined-stream loss-clustering PAUSE: if combined(taker+zmaker)
BREAKER_MIN=10                              # rolling-10 has >=K losses -> pause the taker (hot regime). 0=off.
ETHPAUSE=("--ethpause" in sys.argv)         # eth-specific: pause eth entries at combined roll10>=2 (eth -EV in bad phase; btc kept). Validated 2026-06-21 held-out +$24.75
ROLL_AGE_CAP=float(_argval("--rollage","7200"))  # only count roll losses within 2h (fix sparse-stream staleness — stale 7h losses must not keep eth paused). Added 2026-06-21
ZMAKER_FILE=os.path.join(ROOT,"data","multi_window_engine_live.jsonl")  # zmaker outcomes for the combined stream
# RESTORED 2026-06-10 pm: the morning removal was an n=12 overreaction. Full 197 LIVE fills: vol>=6.5 bucket -$39.55 (68% win) vs vol<6.5 +$6.50 (79%); holds in BOTH time-halves (skip -0.27/sh vs keep -0.10 early; -0.46 vs +0.19 late). Same-day proof: removal afternoon -> eth vol>=9 went 46% win, -$33.30/26 trades = the entire account bleed. Gate skips still outcome-tracked (reason high_vol) so forward validation continues.
SHARES=5
DURS=[("5m",300,308,240)]  # (name, window_secs, settle_after, win_eval_offset). 5m only for now.
MAX_CONCURRENT=int(_argval("--maxconc","3")); MAX_PER_COIN=2; MAX_TOTAL_ORDERS=200; STOP_LOSS=float(_argval("--stop","-15.0"))
_sfx=("_"+_TAG) if _TAG else ""
OUTF=os.path.join(ROOT,"data",f"early_taker_probe{_sfx}.jsonl"); LOG=os.path.join(ROOT,"data",f"early_taker_probe{_sfx}.log")
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
async def kopen(c,sym,st):
    """binance 1m kline OPEN at window start = the reference for lead (matches the backtest)."""
    try:
        k=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":st*1000,"limit":1},timeout=8)).json()
        return float(k[0][1])
    except: return None
# --- COINBASE parallel signal (to validate binance-vs-coinbase live, goal #2) ---
CBSYM={"btc":"BTC-USD","eth":"ETH-USD"}; _cbopen={}
async def cb_now(c,coin):
    try:
        r=(await c.get(f"https://api.exchange.coinbase.com/products/{CBSYM[coin]}/ticker",timeout=8)).json(); return float(r["price"])
    except: return None
async def cb_open(c,coin,st):
    key=(coin,st)
    if key in _cbopen: return _cbopen[key]
    try:
        # NOTE: start/end unix params return [] on this API — fetch recent 1m candles and find time==st
        k=(await c.get(f"https://api.exchange.coinbase.com/products/{CBSYM[coin]}/candles",params={"granularity":60},timeout=8)).json()
        for row in k:  # [time, low, high, open, close, volume], newest first
            if int(row[0])==st:
                op=float(row[3]); _cbopen[key]=op; return op
    except: pass
    return None  # don't cache a miss
async def cb_lead_at(c,coin,st,side):
    """coinbase lead (bps, toward Up) right now, using coinbase's OWN window open. None if unavailable."""
    cbn=await cb_now(c,coin); cbo=await cb_open(c,coin,st)
    if cbn and cbo: return round(math.log(cbn/cbo)*1e4,1)
    return None
_volcache={"t":0.0,"v":None,"f":None}
# VOL gate symbol+cap. Default BTCUSDT/6.5 (btc/eth instance UNCHANGED). A SOL instance passes --volsym SOLUSDT
# --volcap 10.0 to gate on SOL's OWN vol (SOL vol is ~50% higher than BTC; 10.0 = the BTC-6.5-equivalent 70th
# percentile of SOL vol, distribution-matched 2026-06-15, NOT a guess). Captures SOL's idiosyncratic chop that
# a BTC-vol gate would miss.
VOL_SYM=_argval("--volsym","BTCUSDT")
async def btc_regime(c):
    """(vol30, flip60) for VOL_SYM: vol30 = pstdev of the LAST 30 1m log-returns in bps;
    flip60 = sign-alternation rate of the last 60 1m returns (orthogonal regime axes, 2026-06-11)."""
    if time.time()-_volcache["t"]<60 and _volcache["v"] is not None: return _volcache["v"],_volcache["f"]
    try:
        k=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":VOL_SYM,"interval":"1m","limit":61},timeout=8)).json()
        cl=[float(x[4]) for x in k]; rets=[math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))]
        r30=rets[-30:]; m=sum(r30)/len(r30); v=(sum((x-m)**2 for x in r30)/len(r30))**0.5
        sg=[1 if x>=0 else -1 for x in rets]
        fl=sum(1 for i in range(1,len(sg)) if sg[i]!=sg[i-1])/(len(sg)-1)
        _volcache["t"]=time.time(); _volcache["v"]=round(v,2); _volcache["f"]=round(fl,3)
        return _volcache["v"],_volcache["f"]
    except: return None,None
_cvolcache={}  # sym -> (t, vol30)
async def coin_vol30(c,sym):
    """The COIN's OWN vol30 (pstdev of last 30 1m log-returns, bps). DATA-ONLY (2026-06-16): logged so we
    can split REAL live fills by z=|lead|/coin_vol30 and test whether z>=2.5-gating the EARLY taker helps
    (entry-timing study: early+z had the biggest buy-below-fair edge). NOT used for any trade decision."""
    cc=_cvolcache.get(sym)
    if cc and time.time()-cc[0]<60: return cc[1]
    try:
        k=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","limit":31},timeout=8)).json()
        cl=[float(x[4]) for x in k]; rets=[math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))]
        m=sum(rets)/len(rets); v=(sum((x-m)**2 for x in rets)/len(rets))**0.5
        _cvolcache[sym]=(time.time(),round(v,2)); return round(v,2)
    except: return None
_brkcache={"t":0.0,"v":(0,0)}
def _ws_of(slug):
    try: return int(slug.rsplit("-",1)[1])
    except: return None
def combined_roll10():
    """Loss-clustering regime signal for the taker = COMBINED (taker+zmaker) rolling-10 loss count.
    Reads the tail of our own settled fills + the z-maker's settled fills, merges by window-start, takes the
    last 10 outcomes. Validated 2026-06-18 (bt_taker_breaker.py): combined pause >=K=3 is +EV held-out & the
    own-stream is BACKWARDS (pauses winners) — same finding as the z-maker cell. Returns (losses, n)."""
    if time.time()-_brkcache["t"]<30: return _brkcache["v"]
    rows=[]
    for f,is_taker in ((OUTF,True),(ZMAKER_FILE,False)):
        try:
            with open(f,encoding="utf-8") as fh: lines=fh.readlines()[-120:]
        except FileNotFoundError: continue
        for l in lines:
            if not l.strip(): continue
            try: o=json.loads(l)
            except: continue
            if is_taker:
                if o.get("kind")!="entry" or o.get("won") is None: continue
            else:
                if o.get("filled") is not True or o.get("won") is None: continue
            w=_ws_of(o.get("slug",""))
            if w: rows.append((w,bool(o["won"])))
    rows.sort(key=lambda x:x[0]); last=rows[-10:]
    _cut=time.time()-ROLL_AGE_CAP   # stale losses (>2h, frozen in a sparse last-10) don't count
    v=(sum(1 for w,won in last if not won and w>=_cut), len(last)); _brkcache["t"]=time.time(); _brkcache["v"]=v
    return v
async def toks(c,slug):
    try:
        arr=(await c.get(GAMMA,params={"slug":slug},timeout=10)).json()
        if arr:
            ids=json.loads(arr[0]["clobTokenIds"]); outs=json.loads(arr[0]["outcomes"])
            return ids[outs.index("Up")],ids[outs.index("Down")]
    except: pass
    return None,None
async def topask(c,tok):
    """lowest ask = the taker BUY price we'd pay."""
    try:
        b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok},timeout=8)).json()
        asks=sorted(float(a["price"]) for a in b.get("asks",[]) if float(a["size"])>0 and 0<float(a["price"])<1)
        return asks[0] if asks else None
    except: return None
async def our_fill(c,proxy,slug,side):
    """REAL avg fill price of OUR BUY on this slug+outcome (from our activity) — measures true taker cost
    incl. any walk, vs the ask we read. None if not found yet."""
    try:
        a=(await c.get("https://data-api.polymarket.com/activity",params={"user":proxy,"limit":40},timeout=10)).json()
        fills=[(x.get("price"),x.get("size") or 0) for x in a if isinstance(x,dict) and x.get("type")=="TRADE" and (x.get("side") or "").upper()=="BUY" and x.get("slug")==slug and x.get("outcome")==side and x.get("price")]
        tot=sum(s for _,s in fills)
        if tot>0: return sum(p*s for p,s in fills)/tot
    except: pass
    return None
async def kwin(c,sym,st,wa=240):
    try:
        k1=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":st*1000,"limit":1},timeout=8)).json()
        k2=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":(st+wa)*1000,"limit":1},timeout=8)).json()
        return "Up" if float(k2[0][4])>=float(k1[0][1]) else "Down"
    except: return None
def band(p):
    return "<0.5" if p<0.5 else "0.5-0.65" if p<0.65 else "0.65-0.75" if p<0.75 else "0.75-0.85" if p<0.85 else ">=0.85"
async def main():
    cli=None; proxy=None; realized=0.0; orders=0; halted=False; W={}; entered_st=set()  # window-start-times already taken (one coin per window = no correlated btc+eth double-bet)
    if PLACE:
        cli=trader(); proxy=os.environ.get("POLY_PROXY")
        try: bal=float(cli.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6; log(f"LIVE wallet ${bal:.2f}")
        except Exception as e: log(f"bal err {str(e)[:50]}")
    async with httpx.AsyncClient() as c:
        log(f"early_taker_probe START [{'LIVE --place %dsh/conc%d/stop$%g'%(SHARES,MAX_CONCURRENT,STOP_LOSS) if PLACE else 'DRY(reads real ask, no order)'}] fire on lead>=%g & ask<%g & offset<=%ds"%(LEAD_TRIG,PRICE_CAP,MAX_OFFSET))
        while _run:
            t=now()
            for coin,sym in COINS.items():
                for dname,dsec,settle_at,win_at in DURS:
                    ws=int(t//dsec)*dsec; slug=f"{coin}-updown-{dname}-{ws}"
                    if slug not in W:
                        up,dn=await toks(c,slug)
                        if up:
                            op=await kopen(c,sym,ws)
                            W[slug]={"coin":coin,"sym":sym,"st":ws,"up":up,"dn":dn,"open":op,
                                     "entered":False,"order":None,"cross":None,"spike":None,"settled":False,"settle_at":settle_at,"win_at":win_at}
            for slug,w in list(W.items()):
                sec=t-w["st"]
                if w["open"] is None: w["open"]=await kopen(c,w["sym"],w["st"]); continue
                # === PHASE 1: detect the CROSS (lead first >=8) — record candidate, do NOT enter yet ===
                if w["cross"] is None and not w["entered"] and w["spike"] is None and sec<=MAX_OFFSET:
                    px=await bpx(c,w["sym"])
                    if px:
                        lead=math.log(px/w["open"])*1e4; side="Up" if lead>=0 else "Down"
                        if abs(lead)>=LEAD_TRIG:
                            tok0=w["up"] if side=="Up" else w["dn"]; ask0=await topask(c,tok0)
                            bv,fl=await btc_regime(c)
                            w["cross"]={"ts":t,"side":side,"lead":round(lead,1),"offset":round(sec),"ask0":round(ask0,3) if ask0 else None,
                                        "cbe":await cb_now(c,w["coin"]),"bv":bv,"fl":fl,"cvol":await coin_vol30(c,w["sym"]),"confirmed":False}
                            log(f"[CROSS] {slug} {side} lead{lead:+.0f}@{sec:.0f}s ask{ask0} — wait {CONFIRM_SEC}s to confirm")
                # === PHASE 2: after CONFIRM_SEC re-check; enter if still >=8 same side, else mark SPIKE (track only) ===
                elif w["cross"] is not None and not w["entered"] and w["spike"] is None:
                    cr=w["cross"]
                    # INSTRUMENTATION 2026-06-15 (data-only, no trade change): during the confirm wait, sample the
                    # lead+ask trajectory each tick -> evaluate whether a SHORTER confirm captures the priced_in pocket
                    # (+$75/438 @ +0.172EV at cross price) before the favorite is bid past the 0.90 cap.
                    if not cr["confirmed"] and t<cr["ts"]+CONFIRM_SEC:
                        pxs=await bpx(c,w["sym"])
                        if pxs:
                            ls=math.log(pxs/w["open"])*1e4
                            tks=w["up"] if cr["side"]=="Up" else w["dn"]; aks=await topask(c,tks)
                            cr.setdefault("traj",[]).append({"dt":round(t-cr["ts"]),"lead":round(ls,1),"ask":round(aks,3) if aks else None})
                    if not cr["confirmed"] and t>=cr["ts"]+CONFIRM_SEC:
                        px=await bpx(c,w["sym"]); lead2=math.log(px/w["open"])*1e4 if px else 0.0
                        if abs(lead2)>=LEAD_TRIG and (lead2>=0)==(cr["side"]=="Up"):
                            cr["confirmed"]=True; cr["lead2"]=round(lead2,1)
                            log(f"[CONFIRM] {slug} {cr['side']} lead {cr['lead']}->{lead2:+.0f} held — entering")
                        else:  # faded = false spike -> NO trade, track its outcome for the A/B
                            w["spike"]={**cr,"lead2":round(lead2,1),"reason":"faded"}
                            log(f"[SPIKE-SKIP] {slug} {cr['side']} lead {cr['lead']}->{lead2:+.0f} faded — no trade, tracking outcome")
                    if cr["confirmed"] and not w["entered"]:
                        tok=w["up"] if cr["side"]=="Up" else w["dn"]; ask=await topask(c,tok)
                        if ask:
                            _brk_l,_brk_n=combined_roll10()
                            cr["roll10"]=_brk_l; cr["roll10n"]=_brk_n
                            if cr.get("bv") is not None and cr["bv"]>=VOL_CAP:
                                w["spike"]={**cr,"reason":"high_vol","ask":round(ask,3)}
                                log(f"[VOL-SKIP] {slug} {cr['side']} btc_vol{cr['bv']:.1f}>=cap{VOL_CAP} — paused (high vol)")
                            elif ETHPAUSE and w["coin"]=="eth" and _brk_n>=BREAKER_MIN and _brk_l>=2:
                                w["spike"]={**cr,"reason":"eth_pause","ask":round(ask,3)}
                                log(f"[ETH-PAUSE] {slug} {cr['side']} combined roll10={_brk_l}/{_brk_n}>=2 — eth -EV in bad phase, paused (btc unaffected; tracking)")
                            elif BREAKER_K>0 and _brk_n>=BREAKER_MIN and _brk_l>=BREAKER_K:
                                w["spike"]={**cr,"reason":"breaker","ask":round(ask,3)}
                                log(f"[BREAKER-SKIP] {slug} {cr['side']} combined roll10={_brk_l}/{_brk_n}>={BREAKER_K} — hot regime, paused (tracking outcome)")
                            elif cr.get("fl") is not None and cr["fl"]>FLIP_CAP:
                                w["spike"]={**cr,"reason":"high_flip","ask":round(ask,3)}
                                log(f"[FLIP-SKIP] {slug} {cr['side']} flip60 {cr['fl']:.2f}>{FLIP_CAP} — choppy regime, no trade, tracking outcome")
                            elif ask>=PRICE_CAP-0.01:  # cap the PLACED price (ask+1c marketable limit), not the ask: 6 live fills landed >=0.85 via slippage, -$5.55, violating the never-buy->=0.85 rule
                                w["spike"]={**cr,"reason":"priced_in","ask":round(ask,3)}
                                log(f"[SKIP-PRICED-IN] {slug} {cr['side']} confirmed but ask{ask:.3f}>=cap")
                            elif w["st"] in entered_st:
                                w["spike"]={**cr,"reason":"correlated","ask":round(ask,3)}
                                log(f"[CORR-SKIP] {slug} {cr['side']} — sibling coin already taken")
                            elif PLACE and (halted or orders>=MAX_TOTAL_ORDERS or realized<=STOP_LOSS):
                                if realized<=STOP_LOSS and not halted: log("=== STOP-LOSS HALT ==="); halted=True
                            elif PLACE and (sum(1 for ww in W.values() if ww.get("order") and not ww["order"].get("settled_done"))>=MAX_CONCURRENT
                                            or sum(1 for ww in W.values() if ww["coin"]==w["coin"] and ww.get("order") and not ww["order"].get("settled_done"))>=MAX_PER_COIN):
                                pass  # at cap
                            else:
                                if PLACE:
                                    placed=round(min(ask+0.01,0.97),2)
                                    try:
                                        r=cli.place_limit_order(token_id=tok,price=placed,size=SHARES,side="BUY",post_only=False)
                                        oid=getattr(r,"order_id",None) or getattr(r,"id",None)
                                    except Exception as ex: log(f"  taker-blocked/err {slug}: {str(ex)[:80]}"); w["entered"]=True; continue
                                    if not oid: w["entered"]=True; continue
                                    orders+=1
                                    log(f"*** TAKER #{orders} {slug} {cr['side']} {SHARES}sh placed@{placed} (ask{ask:.3f} cross{cr['lead']}@{cr['offset']}s->confirm{cr.get('lead2')}@{sec:.0f}s) ***")
                                    w["entered"]=True; entered_st.add(w["st"])
                                    w["order"]={"side":cr["side"],"ask":round(ask,3),"ask0":cr["ask0"],"placed":placed,"paid":None,"oid":oid,"filled":False,
                                                "lead":cr["lead"],"lead2":cr.get("lead2"),"cb_entry":cr["cbe"],"cross_off":cr["offset"],"offset":round(sec),"btc_vol":cr["bv"],"flip60":cr.get("fl"),"traj":cr.get("traj"),"coin_vol30":cr.get("cvol"),"zscore":(round(abs(cr.get("lead2") or cr["lead"])/cr["cvol"],2) if cr.get("cvol") else None),"roll10":cr.get("roll10"),"roll10n":cr.get("roll10n")}
                                else:
                                    log(f"[DRY] would TAKER {slug} {cr['side']} @ ask {ask:.3f} (cross{cr['lead']}@{cr['offset']}s->confirm@{sec:.0f}s)")
                                    w["entered"]=True; entered_st.add(w["st"])
                                    w["order"]={"side":cr["side"],"ask":round(ask,3),"ask0":cr["ask0"],"placed":round(ask,3),"paid":round(ask,3),"oid":None,"filled":True,
                                                "lead":cr["lead"],"lead2":cr.get("lead2"),"cb_entry":cr["cbe"],"cross_off":cr["offset"],"offset":round(sec),"btc_vol":cr["bv"],"flip60":cr.get("fl"),"traj":cr.get("traj"),"coin_vol30":cr.get("cvol"),"zscore":(round(abs(cr.get("lead2") or cr["lead"])/cr["cvol"],2) if cr.get("cvol") else None),"roll10":cr.get("roll10"),"roll10n":cr.get("roll10n")}
                # poll the real fill (PLACE) — capture true avg cost vs the ask we read
                if PLACE and cli and w.get("order") and not w["order"]["filled"]:
                    o=w["order"]
                    try:
                        od=cli.get_order(order_id=o["oid"]); mt=float(getattr(od,"size_matched",0) or 0)
                        if mt>=SHARES-1e-6:
                            rp=await our_fill(c,proxy,slug,o["side"])
                            o["paid"]=round(rp,3) if rp else o["placed"]; o["filled"]=True
                            log(f"  *** FILLED {slug} real@{o['paid']:.3f} (ask {o['ask']:.3f}, slip {(o['paid']-o['ask'])*100:+.1f}c band {band(o['paid'])}) ***")
                    except: pass
                # --- settle ---
                if sec>w["settle_at"] and not w["settled"]:
                    w["settled"]=True
                    o=w.get("order")
                    if o:
                        if PLACE and cli and not o["filled"]:  # never filled -> cancel, no trade
                            try: cli.cancel_order(order_id=o["oid"])
                            except: pass
                            log(f"SETTLE {slug} order UNFILLED -> canceled (no trade)")
                        else:
                            win=await kwin(c,w["sym"],w["st"],w["win_at"])
                            won=(o["side"]==win) if win else None
                            paid=o["paid"] if o["paid"] is not None else o["placed"]
                            pnl=(((1-paid) if won else -paid)*SHARES) if won is not None else 0.0
                            if PLACE and won is not None: realized+=pnl
                            # coinbase lead: open from candle (now closed) + price we captured at entry
                            cbo=await cb_open(c,w["coin"],w["st"]); cbe=o.get("cb_entry")
                            cb_lead=round(math.log(cbe/cbo)*1e4,1) if (cbe and cbo) else None
                            cb_agree=(cb_lead is not None) and ((cb_lead>=0)==(o["side"]=="Up"))
                            row={"slug":slug,"coin":w["coin"],"kind":"entry","winner":win,"side":o["side"],"won":won,"ask":o["ask"],"ask0":o.get("ask0"),"paid":round(paid,3),
                                 "slip_c":round((paid-o["ask"])*100,1),"band":band(paid),"lead":o["lead"],"lead2":o.get("lead2"),"cross_off":o.get("cross_off"),"cb_lead":cb_lead,"cb_agree":cb_agree,"offset":o["offset"],"pnl":round(pnl,2),"btc_vol":o["btc_vol"],"flip60":o.get("flip60"),"traj":o.get("traj"),"coin_vol30":o.get("coin_vol30"),"zscore":o.get("zscore"),"roll10":o.get("roll10"),"roll10n":o.get("roll10n"),"live":PLACE}
                            open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
                            log(f"SETTLE {slug} win={win} {o['side']} paid@{paid:.3f}(ask{o['ask']:.3f}) {'WON' if won else 'LOST'} pnl=${pnl:+.2f}{' cum$%+.2f'%realized if PLACE else ''}")
                    elif w.get("spike"):  # A/B: a cross that we did NOT trade (faded/priced_in/correlated) -> track would-it-have-won
                        sp=w["spike"]; win=await kwin(c,w["sym"],w["st"],w["win_at"])
                        would=(sp["side"]==win) if win else None
                        row={"slug":slug,"coin":w["coin"],"kind":"spike","reason":sp.get("reason"),"side":sp["side"],"winner":win,"would_win":would,
                             "cross_lead":sp["lead"],"lead2":sp.get("lead2"),"cross_off":sp["offset"],"ask0":sp.get("ask0"),"btc_vol":sp.get("bv"),"flip60":sp.get("fl"),"traj":sp.get("traj"),"coin_vol30":sp.get("cvol"),"zscore":(round(abs(sp.get("lead2") or sp["lead"])/sp["cvol"],2) if sp.get("cvol") else None),"roll10":sp.get("roll10"),"roll10n":sp.get("roll10n"),"live":PLACE}
                        open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
                        log(f"SPIKE-SETTLE {slug} {sp['side']}({sp.get('reason')}) winner={win} would_have_{'WON' if would else 'LOST'}")
                    del W[slug]
            await asyncio.sleep(4)
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
