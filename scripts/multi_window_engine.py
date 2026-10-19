"""multi_window_engine.py — CONCURRENT multi-window taker engine.
Evolution of real_maker_test.py: instead of ONE position at a time (serial, holds to settle
before looking again), it opens EVERY qualifying btc/eth 5m window concurrently, each held to
its own settle. This is the frequency lever (~2x vs serial) — but multi-position = CORRELATED
tail risk (same-coin positions reverse together), so it adds 3 extra risk caps on top of the
single-window hard limits.

Run DRY (no --place) to observe concurrency/frequency with no money.  Run --place for real.
Wallet 0x149200 is COMPROMISED (pk exposed) — tiny only; ROTATE before any scale-up.
"""
import asyncio, json, os, sys, time, math, datetime, signal, statistics
from collections import defaultdict, deque
import httpx
try: import websockets
except ImportError: print("pip install websockets"); sys.exit(1)
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACE=("--place" in sys.argv)   # default DRY (observe only); --place = real money
def _argval(flag,default=None):
    if flag in sys.argv:
        i=sys.argv.index(flag)
        if i+1<len(sys.argv): return sys.argv[i+1]
    return default
# --coins lets a SEPARATE instance run a different coin set (e.g. SOL maker probe) WITHOUT touching the
# btc/eth instance. NO --coins = default UNCHANGED (PLACE->btc/eth, DRY->5coins). --tag suffixes files.
_ALLCB={"btc":"BTC-USD","eth":"ETH-USD","sol":"SOL-USD","xrp":"XRP-USD","doge":"DOGE-USD"}
_ALLBIN={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT","xrp":"XRPUSDT","doge":"DOGEUSDT"}
_coins_arg=_argval("--coins",None)
_TAG=_argval("--tag","")
if _coins_arg: _SEL=[c for c in _coins_arg.split(",") if c in _ALLCB]
else: _SEL=(["btc","eth"] if PLACE else ["btc","eth","sol","xrp","doge"])
# ---- HARD RISK LIMITS (single-window, preserved) ----
SHARES=5; STOP_LOSS=(float(_argval("--stop","-30.0")) if "--place" in sys.argv else -1e9); LATE_FRAC=0.55; THR_BPS=6.0; MIN_TTL=25; MAXNOTIONAL=27.0   # raised 19.5->27 to admit the 28sh deep-calm cell (28*0.95=26.6); concurrent risk still capped by MAX_CONCURRENT_NOTIONAL
CELL_SHARES=int(_argval("--cellshares","20")); CELL_LO=0.90; CELL_HI=float(_argval("--cellhi","0.93"))   # default 20 (btc/eth, validated). SOL probe: --cellshares 5 (flat, no upsize — SOL cell unvalidated live).
# CELL_HI lowered 0.95->0.93 (2026-06-30, all-history backtest): B in [0.93,0.95) is the favorite-longshot OVERPRICED
# zone, robustly -EV across 2 independent DRY datasets (06-04..08 & 06-14..30, n=1816/139 rev) and all 3 time-thirds
# (cap@0.93 +69 pooled, ROBUST). So B>=0.93 -> NOT in_cell -> base 5sh (still trades, just not the 20sh cell size).
# Gives up ~46% of cell wins but each high-bid win is ~$1 while each avoided loss is ~$18 (favorite-longshot asymmetry).
# Revert with --cellhi 0.95. Pairs with the wallet_killswitch (catches the irreducible low-bid reversal tail).
# CIRCUIT BREAKER (2026-06-17, VALIDATED): loss outcomes CLUSTER (regime persists) — runs-test z=-2.37, and
# P(loss|prev10>=2 losses)~21% vs ~10% baseline, INDEPENDENT of vol (+5.3pp lift even in low-vol). The cell
# (0.90-0.95) is -EV during a hot streak (22% loss @0.92). So when recent-10 outcomes have >=BREAKER_K losses,
# DOWNSIZE the cell 20->5sh until it cools. Backtest: +$17-23 net over the period incl the held-out drawdown.
BREAKER_K=int(_argval("--breakerk","2")); BREAKER_MIN=10
ROLL_AGE_CAP=float(_argval("--rollage","7200"))   # only count roll losses within this many secs (2h). Fixes sparse-stream staleness: a 6-7h-old loss frozen in the last-10 (when fills are slow) must NOT keep the breaker/eth-pause armed. Added 2026-06-21 after eth-pause got stuck on 7h-old losses.
ETHPAUSE=("--ethpause" in sys.argv)   # eth-specific bad-phase pause: skip eth entries while combined breaker armed (eth -EV armed/G-3.5; btc +EV armed/G+1.9 -> keep btc). Resume eth when combined cools. Validated 2026-06-21 (held-out +$24.75)   # arm only after >=10 fills; rolling window = last 10
# DEEP-CALM upside tier (2026-06-17, symmetric to the breaker): when the last 10 outcomes are ALL wins
# (roll10==0), the regime is calmest -> modest upsize 20->28sh (=1/4-Kelly at ~95% cell win on $280 wallet,
# bankroll-justified, NOT 100). Only for the validated btc/eth 20sh cell; SOL (cellshares 5) stays flat.
CALM_SHARES = (int(_argval("--calmshares","28")) if CELL_SHARES>=20 else CELL_SHARES)
# TIERED SIZING — SCALE-UP 2026-06-13 (cell 10->20, user-approved after
                     # the 100-fill review PASSED: cell 113/113, zero-loss 95% lower bound ~97% vs breakeven 92.7%,
                     # perfect in EVERY slice incl 10sh 57/57). Green light = 10sh filled AS WELL AS 5sh (47% vs 45%) =
                     # no fill degradation at 2x; real-market depth absorbs 20sh routinely (18% of 0.90-0.95 fills >=20sh).
                     # Base stays 5sh (only the statistically-proven cell is scaled; <0.90 is -EV, 0.95 thin). Single 20sh
                     # cell loss = -$18.6, so STOP_LOSS raised -15->-30 (one cell loss won't halt; two will). 30+sh untested
                     # (book thins above ~30sh). REVERT to 10sh if 20sh fill-rate < 35% OR cell win < 95% over next ~30 fills.
                     # 0.95+ excluded deliberately: 14/15 wins still NET NEGATIVE (certainty priced in).
# STOP_LOSS gated on PLACE: live protects real money at -$15; DRY is pure data collection -> NEVER self-exit on paper PnL
# (it kept dying mid-collection by hitting -15 in down regimes; watchdog restarted but data had gaps).
ONLY_5M=(PLACE)   # PLACE/live = 5m only (validated); DRY = 5m+15m forward data collection (15m never sampled live before)
# --dur: dedicated duration instance. ""=default (unchanged); "15m"=15m-ONLY live probe (btc 15m late maker
# validated +EV in DRY: ~94% win/+$15.67, 1c spread, low adverse-selection); "5m"=5m-only. The engine's
# window/entry/settle logic is already duration-generic (LATE_FRAC x dur), so a 15m instance just needs this gate.
_DUR=_argval("--dur","")
VOLFLOOR=float(_argval("--volfloor","0"))   # skip PLACE entry if vol30 < this (low-vol z-inflation gate). 15m uses 5; 5m default 0 (no gate).
if _DUR=="15m": _DURS=(("15m",900),)
elif _DUR=="5m": _DURS=(("5m",300),)
else: _DURS=((("5m",300),) if ONLY_5M else (("5m",300),("15m",900)))
TAKER=False   # 2026-06-07: switched to MAKER (post bid+0.01, post_only) on z>=2.5 windows — z-selection x
              # cheap maker entry (eebde's edge). Different from the failed lead>=5 maker (weak selection).
# PLACE (real money) = btc/eth ONLY (alts verified -EV; 5-coin multi-window = the -$95 bankruptcy).
# DRY = 5 coins for continued data collection.
ASSETS={c:_ALLCB[c] for c in _SEL}   # derived from _SEL (default = old btc/eth-if-PLACE / 5coins-if-DRY)
ENTRY_MAXLEAD=15.0   # PLACE entry: window must have peaked >= this |lead| (validated single-window filter)
ENTRY_Z=2.5          # PLACE entry: z-score = |lead|/vol30 must be >= this. The ONLY signal to survive per-day OOS
                     # (2026-06-07): z>=2.5 = 84% win every day, +EV, REGIME-PROOF (vol-normalized move significance).
                     # Replaces max_lead/cushion/accel gates. See scripts/zscore_clean_backtest.py.
CELL_LEAD_FLOOR=float(_argval("--cellleadfloor","14"))  # 2026-07-01: cell band (0.90-0.95) needs |lead|>=14bps at entry.
                     # HARDENED (coin-flip model + TIGHT{3,5,8} + 4-fold OOS). All-offset backtest said 16, but LIVE-MATCHED
                     # (off_frac>=0.55, since live cell enters late via LATE_FRAC=0.55) shows 14 already robust (EV +0.032, all
                     # folds+) keeping more volume — 16 was over-conservative (polluted by early-offset DRY entries the live
                     # cell never makes). Below floor = near-strike favorite = Chainlink coin-flip = -EV. PLACE-only.
                     # btcvol>=5 = candidate 2nd gate (EV +0.044) UNDER FORWARD VALIDATION (btcvol now logged). See combo_livematched.py.
ENTRY_PERSIST=0.0    # REVERTED 2026-06-05: persist FAILED out-of-sample (cut 2 winners/0 losers yesterday, -$4.55;
                     # #2 persist0.51 lost live). In-sample overfit. 0.0 = filter OFF (still LOGGED for DRY validation).
ENTRY_CUSHION=8.0    # PLACE entry: current |lead| at entry must be >= this. FORWARD-VALIDATED 2026-06-06 on DRY
                     # 566 labeled records: |lead|<8 (entered ~at the settlement floor) = 57% win / -0.43 EV vs
                     # |lead|>=8 = 72% / breakeven. The ONLY entry filter to survive a real forward test this run.
CLIMAX_LEAD=30.0; CLIMAX_ACCEL=20.0   # CLIMAX SKIP 2026-06-10 (skip+track): entries with |lead|>=30 AND accel>=20
                     # = spike-climax (move already done, fill = reversal start). LIVE z-era 14 fills -$12.00 (EV -0.86/trade),
                     # DRY btc/eth -$11.50/53, negative on 06-07 AND 06-08 in BOTH datasets. Either condition ALONE is +EV
                     # (lead-only 6/6 +$7.15, accel-only 95% +$5.45 live) -> cut ONLY the intersection. Skips are outcome-
                     # tracked (skipped:"climax", would_win/would_pnl) for forward validation, same pattern as the vol gate.
# ---- MULTI-WINDOW RISK CAPS ----
# DRY (data-gathering): loose caps so we sample EVERY qualifying window per coin (no money at risk).
# REAL (--place): strict caps to bound concurrent + CORRELATED exposure.
if PLACE:
    MAX_CONCURRENT=3          # max simultaneously-open positions
    MAX_PER_COIN=2            # CORRELATION CAP: <= this many concurrent on the SAME coin
    MAX_TOTAL_ORDERS=2000     # lifetime order cap (200->2000 2026-06-14, user-approved: the 200 cap kept silently exiting the MAIN profit engine every ~1.5-2 days, 3 stops with ~3-18min idle gaps each; STOP_LOSS=-30 is the real circuit breaker, this cap is just a far backstop. ~2000 = roughly weekly.)
    MAX_CONCURRENT_NOTIONAL=42.0  # max $ deployed across all open positions at once (20->42 2026-06-13 for 20sh cell:
                                  # allows 2x 20sh cell positions (~$38), or 1 cell + normals; stop -30)
else:
    MAX_CONCURRENT=99; MAX_PER_COIN=99; MAX_TOTAL_ORDERS=10**9; MAX_CONCURRENT_NOTIONAL=10**9
# ---- VALIDATED ENTRY FILTER (unchanged) ----
STRONG_BPS=6.0; EARLY_FLIP_MAX=1; CHOP_MAX=0.45; GATE_PERSIST_SECS=15.0; CANCEL_K=1.0
# ---- SIGNAL-STOP (realistic exit model, DRY only): exit when underlying reverses against us
# and PERSISTS (confirmed), selling at the REAL PM bid then (captures adverse-selection exit price). ----
STOP_BPS=3.0; STOP_CONFIRM_SECS=10.0
PROD2COIN={v:k for k,v in ASSETS.items()}
CB_WS="wss://ws-feed.exchange.coinbase.com"; CB_CANDLES="https://api.exchange.coinbase.com/products/{p}/candles"
GAMMA="https://gamma-api.polymarket.com/markets"
_sfx=("_"+_TAG) if _TAG else ("_live" if PLACE else "")   # --tag overrides; default files UNCHANGED
LOG=os.path.join(ROOT,"data",f"multi_window_engine{_sfx}.log"); OUTF=os.path.join(ROOT,"data",f"multi_window_engine{_sfx}.jsonl")
SNAPF=os.path.join(ROOT,"data","timing_snapshots.jsonl")   # DRY: per-window min2/3/4 lead+PM-price + outcome
# COMBINED-STREAM BREAKER (2026-06-18): main 5m btc/eth z-maker uses the COMBINED (taker+zmaker) recent
# loss stream as the regime signal, not just its own. Validated: for the CELL, combined roll>=2 -> 14.3%
# loss (vs 2.7%, +11.5pp), while OWN roll>=2 was -5.3pp (backwards, downsized winning cells). The taker's
# higher-freq losses are a denser/earlier canary for the reversal regime that also catches the cell.
# Only the main instance passes --combined; SOL/15m do NOT (taker is 5m btc/eth, irrelevant to them).
USE_COMBINED=("--combined" in sys.argv)
_TAKER_F=os.path.join(ROOT,"data","early_taker_probe.jsonl")
_tkc={"t":0.0,"f":[]}
def _ws(slug):
    try: return int(str(slug).rsplit("-",1)[1])
    except: return None
def taker_recent():
    """recent taker settled outcomes (ws, won) from the taker jsonl; cached 30s."""
    if time.time()-_tkc["t"]<30 and _tkc["f"]: return _tkc["f"]
    out=[]
    try:
        if os.path.exists(_TAKER_F):
            for ln in [x for x in open(_TAKER_F,encoding="utf-8") if x.strip()][-80:]:
                try:
                    o=json.loads(ln)
                    if o.get("kind")=="entry" and o.get("won") is not None:
                        w=_ws(o.get("slug",""))
                        if w is not None: out.append((w,bool(o["won"])))
                except: pass
    except: pass
    _tkc["t"]=time.time(); _tkc["f"]=out[-30:]; return _tkc["f"]
def roll10_combined(s):
    """rolling-10 loss count over merged (zmaker-own + taker) recent outcomes, by window-start. Returns (losses, n)."""
    own=[]
    for fl in s.fills[-30:]:
        w=_ws(fl.get("slug",""))
        if w is not None: own.append((w,fl["won"]))
    merged=sorted(own+taker_recent(),key=lambda x:x[0])[-10:]
    _cut=time.time()-ROLL_AGE_CAP   # stale losses (>2h, frozen in a sparse last-10) don't count
    return sum(1 for w,won in merged if not won and w>=_cut), len(merged)
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
    f=os.path.join(ROOT,".env")
    for l in open(f,encoding="utf-8"):
        if "=" in l and not l.startswith("#"):
            k,v=l.strip().split("=",1); os.environ.setdefault(k.strip(),v.strip())
    return os.environ["POLY_PK"],os.environ["POLY_PROXY"]
class St:
    def __init__(s):
        s.px=defaultdict(lambda:None); s.bids=defaultdict(dict); s.asks=defaultdict(dict)
        s.win={}; s.actives={}; s.skips={}; s.done=set(); s.orders_done=0; s.realized=0.0; s.fills=[]; s.ticks=0; s.start_wallet=0.0   # s.done = slugs we ever placed on (one-shot-per-window guard; kills cancel-repost stacking, bug 2026-07-02)
        s.peak_concurrent=0
        # preload recent real outcomes so the CIRCUIT BREAKER is armed immediately after a restart
        try:
            if os.path.exists(OUTF):
                for ln in [x for x in open(OUTF,encoding="utf-8") if x.strip()][-40:]:
                    try:
                        _o=json.loads(ln)
                        if _o.get("filled") is True and _o.get("won") is not None:
                            s.fills.append({"slug":_o.get("slug"),"won":bool(_o["won"]),"pnl":_o.get("pnl",0)})
                    except: pass
                s.fills=s.fills[-15:]
        except: pass
def _prune(b,k,hi):
    if len(b)<=k*2: return
    ks=sorted(b); drop=ks[:-k] if hi else ks[k:]
    for p in drop: b.pop(p,None)
async def cb_ws(s):
    d=1
    while _run:
        try:
            async with websockets.connect(CB_WS,ping_interval=15,open_timeout=12,max_size=16*1024*1024) as ws:
                await ws.send(json.dumps({"type":"subscribe","product_ids":list(ASSETS.values()),"channels":["level2_batch"]}))
                log("Coinbase level2 connected"); d=1
                while _run:
                    m=json.loads(await asyncio.wait_for(ws.recv(),timeout=30))
                    t=m.get("type"); c=PROD2COIN.get(m.get("product_id"))
                    if not c: continue
                    if t=="snapshot":
                        s.bids[c]={float(p):float(z) for p,z in m.get("bids",[])[:300]}
                        s.asks[c]={float(p):float(z) for p,z in m.get("asks",[])[:300]}
                    elif t=="l2update":
                        for ch in m.get("changes",[]):
                            sd,p,z=ch[0],float(ch[1]),float(ch[2]); bk=s.bids[c] if sd=="buy" else s.asks[c]
                            if z==0: bk.pop(p,None)
                            else: bk[p]=z
                        _prune(s.bids[c],300,True); _prune(s.asks[c],300,False)
                    else: continue
                    bb=max(s.bids[c]) if s.bids[c] else None; ba=min(s.asks[c]) if s.asks[c] else None
                    if bb and ba and ba>bb: s.px[c]=(bb+ba)/2; s.ticks+=1
        except Exception as e:
            if not _run: break
            log(f"cb err {str(e)[:40]}"); await asyncio.sleep(d); d=min(30,d*2)
async def cb_open(c,prod,st):
    try:
        iso=lambda t: datetime.datetime.utcfromtimestamp(t).isoformat()
        r=(await c.get(CB_CANDLES.format(p=prod),params={"granularity":60,"start":iso(st-180),"end":iso(st+120)})).json()
        if isinstance(r,list) and r:
            for cd in r:
                if int(cd[0])==st: return float(cd[3])
            return float(min(r,key=lambda cd:abs(int(cd[0])-st))[3])
    except: pass
    return None
async def discovery(s):
    while _run:
        t=int(now())
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                for coin,prod in ASSETS.items():
                    for mt,du in _DURS:
                        base=(t//du)*du
                        for st in (base,base+du):
                            slug=f"{coin}-updown-{mt}-{st}"; settle=st+du; ttl=settle-now()
                            if ttl<MIN_TTL or ttl>du+60 or slug in s.win: continue
                            try:
                                arr=(await c.get(GAMMA,params={"slug":slug})).json()
                                if not arr or arr[0].get("closed"): continue
                                m=arr[0]; ids=json.loads(m["clobTokenIds"]); outs=json.loads(m["outcomes"])
                                up=ids[outs.index("Up")]; dn=ids[outs.index("Down")]; op=await cb_open(c,prod,st)
                                s.win[slug]={"coin":coin,"prod":prod,"start":st,"settle":settle,"dur":du,"up":up,"dn":dn,"open":op,
                                    "leadbuf":deque(maxlen=30),"flips":0,"early_flips":0,"last_side":None,"peak_lead":0.0,"strong_since":None,
                                    "peak_up":0.0,"peak_dn":0.0,"last_flip_t":None,
                                    "snaps":{2:None,3:None,4:None}}
                            except: continue
                for slug,w in list(s.win.items()):
                    if w["open"] is None and w["settle"]-now()>0: w["open"]=await cb_open(c,w["prod"],w["start"])
                    if w["settle"]-now()<-300 and slug not in s.actives:
                        # FINALIZE timing snapshots (DRY only): write min2/3/4 lead+price + outcome
                        if not PLACE and w["coin"] in ("btc","eth") and any(w.get("snaps",{}).values()):
                            try:
                                uw=await resolve_up(w["up"],w["settle"])
                                if uw is not None:
                                    open(SNAPF,"a",encoding="utf-8").write(json.dumps({"slug":slug,"coin":w["coin"],"up_win":uw,"snaps":w["snaps"]})+"\n")
                            except Exception as e: log(f"snapfin {str(e)[:30]}")
                        del s.win[slug]
        except Exception as e: log(f"disc {str(e)[:30]}")
        for _ in range(8):
            if not _run: break
            await asyncio.sleep(1)
async def pm_book(tok):
    # returns (best_bid, best_ask, ask_depth_2c) where ask_depth_2c = total shares offered
    # within 2c of the best ask = how much a taker can buy without moving price >2c (liquidity/thinness
    # metric — the likely reason a whale like ce25 avoids doge).
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok})).json()
        araw=[(float(a["price"]),float(a["size"])) for a in b.get("asks",[]) if float(a["size"])>0 and float(a["price"])<1]
        braw=[(float(a["price"]),float(a["size"])) for a in b.get("bids",[]) if float(a["size"])>0 and float(a["price"])>0]
        asks=sorted(p for p,_ in araw); bids=sorted((p for p,_ in braw),reverse=True)
        ba=asks[0] if asks else None
        adepth=round(sum(z for p,z in araw if p<=ba+0.02),1) if ba is not None else None
        return (bids[0] if bids else None),ba,adepth
    except: return None,None,None
async def resolve_up(up_tok, settle):
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r=(await c.get("https://clob.polymarket.com/prices-history",
                params={"market":up_tok,"startTs":int(settle-120),"endTs":int(settle+400),"fidelity":"1"})).json()
        hist=[float(p["p"]) for p in (r.get("history",[]) if isinstance(r,dict) else [])]
        if not hist: return None
        last=hist[-1]
        if last>=0.90: return True
        if last<=0.10: return False
        return None
    except: return None
def trader():
    pk,proxy=load_env()
    from polymarket import SecureClient
    return SecureClient.create(private_key=pk,wallet=proxy)
async def sampler(s):
    while _run:
        for slug,w in list(s.win.items()):
            if w["open"] is None: continue
            px=s.px.get(w["coin"])
            if px is None: continue
            lead=math.log(px/w["open"])*1e4; side="Up" if lead>=0 else "Down"
            if lead>w["peak_up"]: w["peak_up"]=lead          # directional extremes (never reset) for sharp-flip test
            if lead<w["peak_dn"]: w["peak_dn"]=lead
            if w["last_side"] is not None and side!=w["last_side"]:
                w["flips"]+=1
                if (now()-w["start"])/w["dur"]<0.5: w["early_flips"]+=1
                w["peak_lead"]=abs(lead)
                w["last_flip_t"]=now()                       # time of most recent sign flip (reversal freshness)
            w["last_side"]=side
            w["leadbuf"].append(lead)
            if abs(lead)>w["peak_lead"]: w["peak_lead"]=abs(lead)
            if w.get("lead_early") is None and (now()-w["start"])<90: w["lead_early"]=lead  # early lead for accel (strengthening) filter
            # TIMING SNAPSHOTS (DRY only, btc/eth): capture lead + BOTH-side PM book at min2/3/4
            # (both sides => can simulate eebde-style TWO-SIDED making, not just leading-side)
            if not PLACE and w["coin"] in ("btc","eth") and "snaps" in w:
                agem=(now()-w["start"])/60.0
                for mkk in (2,3,4):
                    if w["snaps"].get(mkk) is None and agem>=mkk and abs(lead)>=4:
                        try: ub,ua,_=await pm_book(w["up"])
                        except: ua=ub=None
                        try: db,da,_=await pm_book(w["dn"])
                        except: da=db=None
                        _a=ua if lead>=0 else da; _b=ub if lead>=0 else db   # leading-side (back-compat)
                        w["snaps"][mkk]={"lead":round(lead,1),"side":side,"ask":_a,"bid":_b,
                                         "up_bid":ub,"up_ask":ua,"dn_bid":db,"dn_ask":da}
            lb=list(w["leadbuf"])
            if len(lb)>=8:
                diffs=[lb[i]-lb[i-1] for i in range(1,len(lb))]
                dch=sum(1 for i in range(1,len(diffs)) if (diffs[i]>0)!=(diffs[i-1]>0))
                choppy = dch > len(diffs)*CHOP_MAX
                atr = statistics.pstdev(diffs)*2.0 if len(diffs)>=4 else 3.0
            else:
                choppy=True; atr=3.0
            retraced = abs(lead) < w["peak_lead"] - max(CANCEL_K*atr,4.0)
            ok = (abs(lead)>=STRONG_BPS and not choppy and not retraced and w["early_flips"]<=EARLY_FLIP_MAX)
            if ok:
                if w["strong_since"] is None: w["strong_since"]=now()
            else:
                w["strong_since"]=None
        await asyncio.sleep(2)
def gate_ready(w):
    return (w.get("strong_since") is not None
            and (now()-w["strong_since"])>=GATE_PERSIST_SECS
            and w["early_flips"]<=EARLY_FLIP_MAX)
def features(s,w,lead):
    # ZERO-COST alpha features (all from in-memory data; snapshot at entry):
    #  persist = |lead|/peak (momentum retained; low=faded/exhausting), slope = lead change last ~10s
    #  (accelerating vs decelerating), obimb = Coinbase L2 bid/ask imbalance within 5bps of mid
    #  (>0 = up-pressure), btc_lead = btc's lead at same window-start (cross-asset leading signal).
    coin=w["coin"]; pk=w.get("peak_lead") or 0.0
    persist=round(abs(lead)/pk,3) if pk>0 else None
    lb=list(w.get("leadbuf") or [])
    slope=round(lb[-1]-lb[-6],1) if len(lb)>=6 else None
    px=s.px.get(coin); imb=None
    bk=s.bids.get(coin) or {}; ak=s.asks.get(coin) or {}
    if px and bk and ak:
        band=px*0.0005
        bsz=sum(z for p,z in bk.items() if p>=px-band); asz=sum(z for p,z in ak.items() if p<=px+band)
        if bsz+asz>0: imb=round((bsz-asz)/(bsz+asz),3)
    btc_lead=None
    if coin!="btc":
        bw=s.win.get(f"btc-updown-5m-{w['start']}"); bpx=s.px.get("btc")
        if bw and bw.get("open") and bpx: btc_lead=round(math.log(bpx/bw["open"])*1e4,1)
    return {"persist":persist,"slope":slope,"obimb":imb,"btc_lead":btc_lead}
_n1h_cache={}   # coin -> (ts, bps); for the |1h| 15-40 skip-gate FORWARD test (DRY only)
def trend_band(n):
    if n is None: return None
    a=abs(n); return "0-15" if a<15 else ("15-40" if a<40 else "40+")
async def net1h_bps(coin):
    """|1h move| (bps) from Coinbase 1-min candles, cached 120s/coin. Computed AT ENTRY for the
    forward test of the |1h| 15-40 skip-gate (so the band is a decision-time label, not post-hoc)."""
    c=_n1h_cache.get(coin)
    if c and now()-c[0]<120: return c[1]
    try:
        async with httpx.AsyncClient(timeout=10) as hc:
            r=await hc.get(CB_CANDLES.format(p=ASSETS[coin]),params={"granularity":60})
        arr=r.json()
        if not isinstance(arr,list) or len(arr)<61: return None
        arr.sort(key=lambda x:x[0],reverse=True)   # newest first
        bps=math.log(arr[0][4]/arr[60][4])*1e4     # close now vs close ~60min ago
        _n1h_cache[coin]=(now(),bps); return bps
    except Exception: return None
_vol_cache={}   # coin -> (ts, vol bps/min); prior-30m realized vol for the z-score gate
async def vol30_bps(coin):
    """Prior-30m realized vol (stdev of 1-min log returns, bps/min) from Coinbase candles, cached 120s/coin.
    For the z-score gate z=|lead|/vol = how many sigma the move is (regime-proof, OOS-validated 2026-06-07)."""
    c=_vol_cache.get(coin)
    if c and now()-c[0]<120: return c[1]
    try:
        async with httpx.AsyncClient(timeout=10) as hc:
            r=await hc.get(CB_CANDLES.format(p=ASSETS[coin]),params={"granularity":60})
        arr=r.json()
        if not isinstance(arr,list) or len(arr)<32: return None
        arr.sort(key=lambda x:x[0],reverse=True)   # newest first
        cl=[arr[i][4] for i in range(31)]
        v=statistics.pstdev([math.log(cl[i]/cl[i+1])*1e4 for i in range(30)])
        _vol_cache[coin]=(now(),v); return v
    except Exception: return None
# === BINANCE-PRIMARY signal (2026-06-08): backtest 97% win vs Coinbase 84% — binance closer to Chainlink settlement ===
BINSYM={c:_ALLBIN[c] for c in _SEL}   # derived from _SEL (default btc/eth unchanged; SOL instance gets SOLUSDT)
_binpx_cache={}; _binopen_cache={}; _binvol_cache={}
async def bin_now(coin):
    c=_binpx_cache.get(coin)
    if c and now()-c[0]<2: return c[1]
    try:
        async with httpx.AsyncClient(timeout=8) as hc:
            r=await hc.get("https://api.binance.com/api/v3/ticker/price",params={"symbol":BINSYM[coin]})
        p=float(r.json()["price"]); _binpx_cache[coin]=(now(),p); return p
    except Exception: return None
async def bin_open(coin,st):
    k=(coin,st)
    if k in _binopen_cache: return _binopen_cache[k]
    try:
        async with httpx.AsyncClient(timeout=8) as hc:
            r=await hc.get("https://api.binance.com/api/v3/klines",params={"symbol":BINSYM[coin],"interval":"1m","startTime":st*1000,"limit":1})
        op=float(r.json()[0][1]); _binopen_cache[k]=op; return op
    except Exception: return None
async def bin_vol30(coin):
    c=_binvol_cache.get(coin)
    if c and now()-c[0]<120: return c[1]
    try:
        async with httpx.AsyncClient(timeout=8) as hc:
            r=await hc.get("https://api.binance.com/api/v3/klines",params={"symbol":BINSYM[coin],"interval":"1m","limit":31})
        cl=[float(x[4]) for x in r.json()]
        v=statistics.pstdev([math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))])
        _binvol_cache[coin]=(now(),v); return v
    except Exception: return None
EEBDE_ADDR="0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
_eeb_cache={"ts":0.0,"map":{}}
async def eebde_favmap():
    """slug -> eebde's VALUE-weighted favorite side, from his recent data-api activity. Cached 15s.
    For the forward test of 'only trade when aligned with eebde's favorite' (DRY 88% aligned vs 42% against)."""
    if now()-_eeb_cache["ts"]<15: return _eeb_cache["map"]
    try:
        async with httpx.AsyncClient(timeout=10) as hc:
            acts=(await hc.get("https://data-api.polymarket.com/activity",params={"user":EEBDE_ADDR,"limit":500})).json()
        val=defaultdict(lambda:defaultdict(float))
        if isinstance(acts,list):
            for a in acts:
                if not isinstance(a,dict) or a.get("type")!="TRADE" or (a.get("side") or "").upper()!="BUY": continue
                o=a.get("outcome"); sl=a.get("slug")
                if o in ("Up","Down") and sl: val[sl][o]+=(a.get("price",0) or 0)*(a.get("size",0) or 0)
        _eeb_cache["map"]={sl:max(d,key=d.get) for sl,d in val.items() if d}; _eeb_cache["ts"]=now()
    except Exception: pass
    return _eeb_cache["map"]
async def try_open(s,cli):
    """Scan all windows; open EVERY qualifying one not already held, subject to concurrency/correlation/notional caps."""
    if len(s.actives)>=MAX_CONCURRENT: return
    for slug,w in list(s.win.items()):
        if len(s.actives)>=MAX_CONCURRENT: break
        if slug in s.actives or slug in s.done: continue   # done = already placed this window once (never re-enter after adverse-cancel; stacking bug 2026-07-02: 8 orders on one eth-15m window -> -$24.56)
        if PLACE and slug in s.skips: continue   # climax-tracked window stays skipped (clean forward validation)
        if s.orders_done>=MAX_TOTAL_ORDERS: break
        ttl=w["settle"]-now(); px=s.px.get(w["coin"])
        if w["open"] is None or px is None: continue
        if (now()-w["start"])/w["dur"]<LATE_FRAC or ttl<MIN_TTL: continue
        cb_lead=math.log(px/w["open"])*1e4   # Coinbase lead — now a LABEL only (binance is primary)
        # BINANCE-PRIMARY entry (2026-06-08): lead/vol/z/side from binance (97% vs CB 84% backtest, closer to Chainlink)
        bnow=await bin_now(w["coin"]); bopen=await bin_open(w["coin"],w["start"]); _vol=await bin_vol30(w["coin"])
        if not (bnow and bopen and _vol and _vol>0): continue
        _btcvol=(_vol if w["coin"]=="btc" else (await bin_vol30("btc") or await bin_vol30("btc")))   # BTC-market vol, one retry on transient miss (forward-validating btcvol>=5 as cell 2nd gate; data-only)
        lead=math.log(bnow/bopen)*1e4        # binance lead = the primary signal
        if abs(lead)<THR_BPS: continue
        accel = ((lead - w["lead_early"])*(1 if lead>=0 else -1)) if w.get("lead_early") is not None else None  # CB-based DRY label
        zscore = round(abs(lead)/_vol,2)
        if PLACE and (zscore is None or zscore < ENTRY_Z): continue   # binance z>=2.5
        if PLACE and VOLFLOOR>0 and _vol < VOLFLOOR: continue   # low-vol z-inflation gate (15m: vol<5 = 77% win, -EV; bt_15m_gate.py)
        # CORRELATION CAP: limit concurrent same-coin positions
        coin_n=sum(1 for a in s.actives.values() if a["coin"]==w["coin"])
        if coin_n>=MAX_PER_COIN:
            continue
        side="Up" if lead>=0 else "Down"; tok=w["up"] if side=="Up" else w["dn"]
        bid,ask,adepth=await pm_book(tok)
        if bid is None or ask is None: continue
        spread=round(ask-bid,3)
        if TAKER: B=round(ask,2); po=False
        else:
            B=round(bid+0.01,2); po=True
            if B>=ask: B=bid
        if USE_COMBINED:
            _roll10,_nstream=roll10_combined(s); _armed=(_nstream>=BREAKER_MIN)   # combined taker+zmaker stream
        else:
            _roll10=sum(1 for fl in s.fills[-10:] if not fl["won"]); _armed=(len(s.fills)>=BREAKER_MIN)
        _breaker=(_armed and _roll10>=BREAKER_K)   # hot streak -> de-risk the cell (5sh)
        _deepcalm=(_armed and _roll10==0)          # last 10 ALL wins -> modest upsize (28sh)
        if PLACE and ETHPAUSE and w["coin"]=="eth" and _breaker:   # eth bad-phase pause (skip eth, keep btc); resume when combined cools
            s.skips[slug]={"slug":slug,"coin":w["coin"],"side":side,"B":B,"ask":ask,"settle":w["settle"],"up":w["up"],
                           "lead":round(lead,1),"max_lead":round(w["peak_lead"],1),"accel":round(accel,1) if accel is not None else None,"zscore":zscore,"vol30":round(_vol,1),"reason":"eth_pause"}
            log(f"[ETH-PAUSE] {slug} {side} skip — combined roll10={_roll10}>=2 (eth -EV in bad phase); btc unaffected, tracking outcome")
            continue
        in_cell=(CELL_LO<=B<CELL_HI)
        if PLACE and (CELL_LO<=B<0.95) and abs(lead)<CELL_LEAD_FLOOR:   # cell lead-floor (hardened OOS): near-strike favorite = coin-flip = -EV
            s.skips[slug]={"slug":slug,"coin":w["coin"],"side":side,"B":B,"ask":ask,"settle":w["settle"],"up":w["up"],
                           "lead":round(lead,1),"max_lead":round(w["peak_lead"],1),"accel":round(accel,1) if accel is not None else None,"zscore":zscore,"vol30":round(_vol,1),"reason":"cell_lead_floor"}
            log(f"[CELL-LEADFLOOR] {slug} {side} B={B} lead={lead:+.0f}<{CELL_LEAD_FLOOR:.0f} — near-strike coin-flip risk, skip (tracking outcome)")
            continue
        if PLACE and in_cell:
            sh=(SHARES if _breaker else (CALM_SHARES if _deepcalm else CELL_SHARES))
        else:
            sh=SHARES
        if not (0.30<=B<=0.95) or B*sh>MAXNOTIONAL: continue
        if PLACE and accel is not None and abs(lead)>=CLIMAX_LEAD and accel>=CLIMAX_ACCEL:
            s.skips[slug]={"slug":slug,"coin":w["coin"],"side":side,"B":B,"ask":ask,"settle":w["settle"],"up":w["up"],
                           "lead":round(lead,1),"max_lead":round(w["peak_lead"],1),"accel":round(accel,1),"zscore":zscore,"vol30":round(_vol,1)}
            log(f"[CLIMAX-SKIP] {slug} {side} lead{lead:+.0f} accel{accel:.0f} B={B} — climax (lead>={CLIMAX_LEAD:.0f}&accel>={CLIMAX_ACCEL:.0f}), no trade, tracking outcome")
            continue
        # NOTIONAL CAP: bound total $ deployed concurrently
        cur_notional=sum(a["B"]*a.get("sh",SHARES) for a in s.actives.values())
        if cur_notional+B*sh>MAX_CONCURRENT_NOTIONAL:
            continue
        if not PLACE:
            g=gate_ready(w); ft=features(s,w,lead)
            n1h=await net1h_bps(w["coin"]); tband=trend_band(n1h)
            wskip=(n1h is not None and 15<=abs(n1h)<40)   # |1h| 15-40 skip-gate would skip this entry
            cushion=round(abs(lead),1)                    # entry cushion = current |lead| above the settlement floor
            low_cush=(abs(lead)<8)                         # <8bps = entered ~at the floor (DRY-flagged: -EV in 2-day data)
            favmap=await eebde_favmap()                    # eebde alignment label (DRY: aligned 88% vs against 42%)
            eeb_fav=favmap.get(slug); eeb_aligned=(eeb_fav==side) if eeb_fav else None
            # SHARP-FLIP labels (DRY tag only): did the lead lead BOTH ways then rebuild on the entry side?
            flip_swing=round(w["peak_up"]-w["peak_dn"],1)                       # total range Up-extreme to Down-extreme
            old_side_peak=round(w["peak_dn"] if side=="Up" else w["peak_up"],1) # how strong the OPPOSITE side got before we flipped to entry side
            since_flip=round(now()-w["last_flip_t"],0) if w.get("last_flip_t") else None  # secs since last sign flip (reversal freshness)
            sharp_flip=(w["flips"]>=1 and abs(old_side_peak)>=8 and abs(lead)>=8 and since_flip is not None and since_flip<=90)
            s.actives[slug]={"slug":slug,"coin":w["coin"],"side":side,"B":B,"ask":ask,"bid":bid,"tok":tok,
                             "settle":w["settle"],"up":w["up"],"oid":"DRY","filled":True,"gated":g,"lead":round(lead,1),"max_lead":round(w["peak_lead"],1),"spread":spread,"adepth":adepth,
                             "rev_since":None,"stop_px":None,"stop_lead":None,"feat":ft,
                             "net1h":round(n1h,1) if n1h is not None else None,"tband":tband,"gate_skip":wskip,
                             "cushion":cushion,"low_cushion":low_cush,"eeb_fav":eeb_fav,"eeb_aligned":eeb_aligned,
                             "accel":round(accel,1) if accel is not None else None,"zscore":zscore,"vol30":round(_vol,1) if _vol else None,
                             "flip_swing":flip_swing,"old_side_peak":old_side_peak,"since_flip":since_flip,"flips":w["flips"],"sharp_flip":sharp_flip}
            s.orders_done+=1; s.peak_concurrent=max(s.peak_concurrent,len(s.actives))
            log(f"[DRY] OPEN #{s.orders_done} {slug} {side}@{B} lead={lead:+.0f}bps net1h={('%.0f'%n1h) if n1h is not None else 'NA'}({tband}{' GATE-SKIP' if wskip else ''}) (conc={len(s.actives)})")
            continue
        try:
            r=cli.place_limit_order(token_id=tok,price=B,size=sh,side="BUY",post_only=po)
        except Exception as e:
            log(f"place exc {str(e)[:80]}"); continue
        oid=getattr(r,"order_id",None) or getattr(r,"id",None); status=getattr(r,"status",None)
        if not oid:
            log(f"  no oid (status={status} err={getattr(r,'error_msg',None)}) skip"); continue
        _pst=round(abs(lead)/w["peak_lead"],2) if w["peak_lead"]>0 else None
        s.actives[slug]={"slug":slug,"coin":w["coin"],"side":side,"B":B,"ask":ask,"bid":bid,"tok":tok,"adepth":adepth,
                         "settle":w["settle"],"up":w["up"],"oid":oid,"filled":False,"sh":sh,
                         "max_lead":round(w["peak_lead"],1),"lead":round(lead,1),"persist":_pst,"accel":round(accel,1) if accel is not None else None,"zscore":zscore,"vol30":round(_vol,1) if _vol else None,
                         "roll10":_roll10,"breaker":_breaker,"deepcalm":_deepcalm,"in_cell":in_cell,"btcvol":round(_btcvol,1) if _btcvol else None}
        s.done.add(slug)   # one shot per window — never re-place this slug (stacking bug fix)
        s.orders_done+=1; s.peak_concurrent=max(s.peak_concurrent,len(s.actives))
        log(f"PLACED #{s.orders_done} {slug} {side} {sh}sh @ {B}{' [CELL]' if (in_cell and sh==CELL_SHARES) else (' [CELL-DEEPCALM:28]' if (in_cell and _deepcalm) else (' [CELL-BREAKER:roll%d->5]'%_roll10 if (in_cell and _breaker) else ''))} (ask={ask} maxLead={w['peak_lead']:.0f} lead={lead:+.0f} persist={_pst} concurrent={len(s.actives)}) oid={str(oid)[:14]}")
async def manage_one(s,cli,slug,o):
    w=s.win.get(slug)
    if not PLACE:
        # CONFIRMED SIGNAL-STOP monitoring (pre-settle): if the underlying reverses against our
        # side and persists >= STOP_CONFIRM_SECS, capture the REAL PM bid then = realistic sell
        # price (adverse-selection exit). Only capture once.
        if o.get("stop_px") is None and w and w.get("open") and o["settle"]-now()>0:
            px=s.px.get(o["coin"])
            if px is not None:
                lead=math.log(px/w["open"])*1e4; our=1 if o["side"]=="Up" else -1
                if our*lead <= -STOP_BPS:
                    if o.get("rev_since") is None: o["rev_since"]=now()
                    elif now()-o["rev_since"]>=STOP_CONFIRM_SECS:
                        eb,ea,_=await pm_book(o["tok"])
                        o["stop_px"]=eb if eb is not None else round(max(0.01,o["B"]-abs(lead)/100),2)
                        o["stop_lead"]=round(lead,1)
                        log(f"[DRY] STOP-CONFIRM {slug} {o['side']} reversed {lead:+.0f}bps -> sell-bid={o['stop_px']}")
                else:
                    o["rev_since"]=None
        if o["settle"]-now()<-5:
            up_win=await resolve_up(o["up"],o["settle"]); waited=now()-o["settle"]
            if up_win is None and waited<180: return
            if up_win is None: log(f"[DRY] {slug} UNRESOLVED"); s.actives.pop(slug,None); return
            won=(up_win and o["side"]=="Up") or ((not up_win) and o["side"]=="Down")
            pnl=(1.0-o["B"])*SHARES if won else (-o["B"]*SHARES)
            # signal-stop pnl: if a confirmed reversal fired, we exited at the real PM bid then
            pnl_stop=((o["stop_px"]-o["B"])*SHARES) if o.get("stop_px") is not None else pnl
            s.realized+=pnl; s.fills.append({"slug":slug,"won":won,"pnl":round(pnl,2)})
            open(OUTF,"a",encoding="utf-8").write(json.dumps({"dry":True,"slug":slug,"coin":o["coin"],"side":o["side"],"B":o["B"],"won":won,"pnl":round(pnl,2),"pnl_stop":round(pnl_stop,2),"stopped":o.get("stop_px") is not None,"stop_px":o.get("stop_px"),"stop_lead":o.get("stop_lead"),"gated":o.get("gated"),"lead":o.get("lead"),"max_lead":o.get("max_lead"),"spread":o.get("spread"),"adepth":o.get("adepth"),"feat":o.get("feat"),"net1h":o.get("net1h"),"tband":o.get("tband"),"gate_skip":o.get("gate_skip"),"cushion":o.get("cushion"),"low_cushion":o.get("low_cushion"),"eeb_fav":o.get("eeb_fav"),"eeb_aligned":o.get("eeb_aligned"),"accel":o.get("accel")})+"\n")
            log(f"[DRY] SETTLED {slug} won={won} hold=${pnl:+.2f} stop=${pnl_stop:+.2f} | cum=${s.realized:.2f} (open={len(s.actives)-1})")
            s.actives.pop(slug,None)
        return
    # cancel-on-adverse while unfilled
    if not o["filled"] and w and w["open"]:
        px=s.px.get(o["coin"])
        if px is not None:
            lead=math.log(px/w["open"])*1e4; cur="Up" if lead>=0 else "Down"
            if cur!=o["side"] or abs(lead)<THR_BPS*0.5:
                # BUG FIX 2026-07-02: o["filled"] is poll-lagged — an order that JUST matched looked unfilled,
                # got canceled+popped here -> ORPHANED position (real shares, never settled/logged = under-record)
                # while the freed slug re-entered -> 8-order stack on one window (-$24.56). Check REAL match first.
                _mt=0.0
                try:
                    _od=cli.get_order(order_id=o["oid"]); _mt=float(getattr(_od,"size_matched",0) or 0)
                except Exception: pass
                if _mt>0:
                    o["filled"]=True; log(f"  CANCEL(adverse) ABORTED {slug}: already matched {_mt}sh -> holding to settle")
                else:
                    try: cli.cancel_order(order_id=o["oid"]); log(f"  CANCEL(adverse) {slug} lead now {lead:+.0f}bps")
                    except Exception as e: log(f"  cancel exc {str(e)[:50]}")
                    s.actives.pop(slug,None); return
    try:
        od=cli.get_order(order_id=o["oid"]); mt=float(getattr(od,"size_matched",0) or 0)
        if mt>=o.get("sh",SHARES)-1e-6 and not o["filled"]:
            o["filled"]=True; log(f"  *** FILLED {slug} {o.get('sh',SHARES)}sh @ {o['B']} ***")
    except Exception as e: log(f"  poll exc {str(e)[:50]}")
    if o["settle"]-now()<-5:
        if not o["filled"]:
            try: cli.cancel_order(order_id=o["oid"]); log(f"  unfilled -> CANCELED {slug}")
            except Exception as e: log(f"  cancel exc {str(e)[:50]}")
            s.actives.pop(slug,None)
        else:
            up_win=await resolve_up(o["up"],o["settle"]); waited=now()-o["settle"]
            if up_win is None and waited<180: return
            _resby="pm"
            if up_win is None:
                # FIX 2026-06-30: PM token often won't resolve to 0/1 on TIGHT-CALL reversals (= most of our LOSSES),
                # leaving last in 0.10-0.90 -> resolve_up returns None -> the loss was silently DROPPED (never logged),
                # systematically inflating logged win-rate. Fall back to the underlying (binance settle vs strike) so
                # the loss gets LOGGED. Flagged resolved_by="binance" (a proxy; may differ from Chainlink on <5bps ties).
                _st=o["settle"]-(900 if "-15m-" in slug else 300)
                _o=await bin_open(o["coin"],_st); _e=await bin_open(o["coin"],o["settle"])
                if _o is None or _e is None:
                    log(f"  {slug} filled but UNRESOLVED (pm+binance) — holding, manual check"); s.actives.pop(slug,None); return
                up_win=(_e>=_o); _resby="binance"
            won=(up_win and o["side"]=="Up") or ((not up_win) and o["side"]=="Down")
            _sh=o.get("sh",SHARES)
            pnl=(1.0-o["B"])*_sh if won else (-o["B"]*_sh)
            s.realized+=pnl; s.fills.append({"slug":slug,"won":won,"pnl":round(pnl,2)})
            open(OUTF,"a",encoding="utf-8").write(json.dumps({"slug":slug,"coin":o["coin"],"side":o["side"],"B":o["B"],"ask":o["ask"],"adepth":o.get("adepth"),"filled":True,"won":won,"pnl":round(pnl,2),"sh":_sh,"max_lead":o.get("max_lead"),"lead":o.get("lead"),"persist":o.get("persist"),"accel":o.get("accel"),"flip_swing":o.get("flip_swing"),"old_side_peak":o.get("old_side_peak"),"since_flip":o.get("since_flip"),"flips":o.get("flips"),"sharp_flip":o.get("sharp_flip"),"zscore":o.get("zscore"),"vol30":o.get("vol30"),"roll10":o.get("roll10"),"breaker":o.get("breaker"),"deepcalm":o.get("deepcalm"),"in_cell":o.get("in_cell"),"btcvol":o.get("btcvol"),"resolved_by":_resby})+"\n")
            try: wnow=float(cli.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6
            except: wnow=None
            wtxt=f" | WALLET=${wnow:.2f} (true Δ ${wnow-s.start_wallet:+.2f})" if wnow is not None else ""
            log(f"  SETTLED {slug} won={won} pnl=${pnl:+.2f} | cum computed=${s.realized:.2f} (open={len(s.actives)-1}){wtxt}")
            s.actives.pop(slug,None)
async def resolve_skips(s):
    """Settle climax-skip tracking rows (no money involved): would_win/would_pnl for forward validation."""
    for slug,k in list(s.skips.items()):
        if k["settle"]-now()<-5:
            up_win=await resolve_up(k["up"],k["settle"])
            if up_win is None:
                if now()-k["settle"]>300: s.skips.pop(slug,None)
                continue
            ww=(up_win and k["side"]=="Up") or ((not up_win) and k["side"]=="Down")
            wp=(1.0-k["B"])*SHARES if ww else (-k["B"]*SHARES)
            open(OUTF,"a",encoding="utf-8").write(json.dumps({"skipped":k.get("reason","climax"),"slug":slug,"coin":k["coin"],"side":k["side"],"B":k["B"],"ask":k["ask"],
                "would_win":ww,"would_pnl":round(wp,2),"lead":k["lead"],"max_lead":k["max_lead"],"accel":k["accel"],"zscore":k["zscore"],"vol30":k["vol30"]})+"\n")
            log(f"[{k.get('reason','climax').upper()}-SKIP-SETTLE] {slug} {k['side']} would_have_{'WON' if ww else 'LOST'} (${wp:+.2f})")
            s.skips.pop(slug,None)
async def loop(s,cli):
    global _run
    while _run:
        if s.orders_done>=MAX_TOTAL_ORDERS and not s.actives:
            log(f"=== DONE: {MAX_TOTAL_ORDERS} orders, all settled. realized=${s.realized:.2f} peak_concurrent={s.peak_concurrent} ==="); break
        if s.realized<=STOP_LOSS:
            log(f"=== STOP-LOSS hit: realized=${s.realized:.2f} <= ${STOP_LOSS} (closing, no new) ===")
            # stop opening new, but let existing settle
            for slug,o in list(s.actives.items()): await manage_one(s,cli,slug,o)
            if not s.actives: break
            await asyncio.sleep(2); continue
        if s.orders_done<MAX_TOTAL_ORDERS:
            await try_open(s,cli)
        for slug,o in list(s.actives.items()):
            await manage_one(s,cli,slug,o)
        if PLACE and s.skips: await resolve_skips(s)
        await asyncio.sleep(2)
    try: wfin=float(cli.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6
    except: wfin=None
    wtxt=f" | WALLET ${s.start_wallet:.2f}->${wfin:.2f} (TRUE Δ ${wfin-s.start_wallet:+.2f})" if (wfin is not None and PLACE) else ""
    log(f"FINAL: {s.orders_done} orders, {len(s.fills)} fills, computed ${s.realized:+.2f}, peak_concurrent={s.peak_concurrent}{wtxt}")
    _run=False
async def main():
    s=St(); cli=trader()
    bal=float(cli.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6
    s.start_wallet=bal
    mode="REAL (--place)" if PLACE else "DRY (observe only, no money)"
    log(f"multi_window_engine START [{mode}] wallet ${bal:.2f} | caps: {SHARES}sh, maxConc={MAX_CONCURRENT}, perCoin={MAX_PER_COIN}, maxOrders={MAX_TOTAL_ORDERS}, stop@${STOP_LOSS}, maxNotional=${MAX_CONCURRENT_NOTIONAL}")
    await asyncio.gather(cb_ws(s),discovery(s),sampler(s),loop(s,cli))
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
