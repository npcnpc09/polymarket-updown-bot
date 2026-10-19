"""real_maker_test.py — TINY REAL-MONEY maker fill test. Posts post_only BIDS on the
underlying-leading side late in updown windows, ONE order at a time, to observe what we
actually FILL at and whether we end up on winners (the one thing backtest/paper can't show).
Buy-only, holds fills to auto-redeem. HARD LIMITS: MAX_ORDERS, stop on cumulative loss.
Wallet 0x149200 is COMPROMISED (pk exposed) — tiny only.
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
# ---- HARD RISK LIMITS ----
SHARES=5; MAX_ORDERS=4; STOP_LOSS=-10.0; LATE_FRAC=0.55; THR_BPS=6.0; MIN_TTL=60; MAXNOTIONAL=5.0  # MIN_TTL 25->60: no entry in last 60s (whipsaw has no recovery room) — see #4 btc Down@0.94 loss
ONLY_5M=True   # validated edge: btc/eth + 5m only (15m & alts are -EV)
TAKER=True     # True: cross the ask (immediate fill, actively load winner); False: post_only maker bid
ASSETS={"btc":"BTC-USD","eth":"ETH-USD"}   # btc/eth ONLY (sol/xrp/doge were -EV noise)
# ---- VALIDATED ENTRY FILTER (ported from winner_skew_maker; only trade clean trends) ----
ENTRY_MAXLEAD=15.0      # window must have peaked at >= this |lead| (clean strong trend) to enter
STRONG_BPS=6.0          # underlying must lead our side by >= this
EARLY_FLIP_MAX=1        # skip windows whose leader flipped >1x in the first half (choppy regime)
CHOP_MAX=0.45           # skip if lead-increments change direction > this fraction (choppy = no trend)
GATE_PERSIST_SECS=15.0  # signal must persist this long before we place (no transient spikes)
CANCEL_K=1.0            # treat as faded if lead retraced from peak by > CANCEL_K*ATR
PROD2COIN={v:k for k,v in ASSETS.items()}
CB_WS="wss://ws-feed.exchange.coinbase.com"; CB_CANDLES="https://api.exchange.coinbase.com/products/{p}/candles"
GAMMA="https://gamma-api.polymarket.com/markets"; YR=31557600.0
LOG=os.path.join(ROOT,"data","real_maker_test.log"); OUTF=os.path.join(ROOT,"data","real_maker_test.jsonl")
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
        s.win={}; s.active=None; s.orders_done=0; s.realized=0.0; s.fills=[]; s.ticks=0
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
                    for mt,du in ((("5m",300),) if ONLY_5M else (("5m",300),("15m",900))):
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
                                    "leadbuf":deque(maxlen=30),"flips":0,"early_flips":0,"last_side":None,"peak_lead":0.0,"strong_since":None}
                            except: continue
                for slug,w in list(s.win.items()):
                    if w["open"] is None and w["settle"]-now()>0: w["open"]=await cb_open(c,w["prod"],w["start"])
                    if w["settle"]-now()<-200: del s.win[slug]
        except Exception as e: log(f"disc {str(e)[:30]}")
        for _ in range(8):
            if not _run: break
            await asyncio.sleep(1)
async def pm_book(tok):
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok})).json()
        asks=sorted(float(a["price"]) for a in b.get("asks",[]) if float(a["size"])>0 and float(a["price"])<1)
        bids=sorted((float(a["price"]) for a in b.get("bids",[]) if float(a["size"])>0 and float(a["price"])>0),reverse=True)
        return (bids[0] if bids else None),(asks[0] if asks else None)
    except: return None,None
async def resolve_up(up_tok, settle):
    # RELIABLE resolution via the Up token's prices-history (persists post-settle, unlike gamma
    # which de-indexes). Last value converges to 1.0 (Up won) or 0.0 (Down won). NOT the convU
    # PM-mid heuristic (that was unreliable and caused PnL mis-marking).
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
    # continuously track each window's underlying lead -> flips, early_flips, choppiness, persistence
    while _run:
        for slug,w in list(s.win.items()):
            if w["open"] is None: continue
            px=s.px.get(w["coin"])
            if px is None: continue
            lead=math.log(px/w["open"])*1e4; side="Up" if lead>=0 else "Down"
            if w["last_side"] is not None and side!=w["last_side"]:
                w["flips"]+=1
                if (now()-w["start"])/w["dur"]<0.5: w["early_flips"]+=1
                w["peak_lead"]=abs(lead)   # leader flipped -> reset peak to new side
            w["last_side"]=side
            w["leadbuf"].append(lead)
            if abs(lead)>w["peak_lead"]: w["peak_lead"]=abs(lead)
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
    # validated entry gate: persistent, non-choppy, low-early-flip trend
    return (w.get("strong_since") is not None
            and (now()-w["strong_since"])>=GATE_PERSIST_SECS
            and w["early_flips"]<=EARLY_FLIP_MAX)

async def loop(s,cli):
    global _run
    while _run:
        # stop conditions — only EXIT when no position is open, so the LAST order is fully
        # settled & accounted (else FINAL hides the last order's outcome -> over-reports losses).
        if s.active is None and (s.orders_done>=MAX_ORDERS or s.realized<=STOP_LOSS):
            why=(f"DONE: {MAX_ORDERS} orders placed" if s.orders_done>=MAX_ORDERS
                 else f"STOP-LOSS realized=${s.realized:.2f} <= ${STOP_LOSS}")
            log(f"=== {why}, all settled. realized=${s.realized:.2f} ==="); break
        # place a NEW order only while under the caps (manage any open position regardless)
        if s.active is None and s.orders_done<MAX_ORDERS and s.realized>STOP_LOSS:
            # find a late leading-side signal
            for slug,w in list(s.win.items()):
                ttl=w["settle"]-now(); px=s.px.get(w["coin"])
                if w["open"] is None or px is None: continue
                if (now()-w["start"])/w["dur"]<LATE_FRAC or ttl<MIN_TTL: continue
                lead=math.log(px/w["open"])*1e4
                if abs(lead)<THR_BPS: continue
                # ENTRY = max_lead band (VALIDATING 2026-06-04): the strict persistence gate was
                # over-filtering (~4 trades/day, skipping ~70 clean strong-trend winners). Switch to
                # "window has shown a strong trend (peak_lead>=ENTRY_MAXLEAD) and is still leading".
                # In-sample today this 4x'd volume to ~27/day at 89% win; forward-validating live.
                if w["peak_lead"] < ENTRY_MAXLEAD:
                    continue
                side="Up" if lead>=0 else "Down"; tok=w["up"] if side=="Up" else w["dn"]
                bid,ask=await pm_book(tok)
                if bid is None or ask is None: continue
                if TAKER:
                    B=round(ask,2); po=False    # TAKER: cross the ask -> immediate fill, actively load the winner
                else:
                    B=round(bid+0.01,2); po=True  # MAKER: post improving bid, wait to be hit
                    if B>=ask: B=bid
                if not (0.30<=B<=0.95) or B*SHARES>MAXNOTIONAL: continue
                # PLACE real order
                try:
                    r=cli.place_limit_order(token_id=tok,price=B,size=SHARES,side="BUY",post_only=po)
                except Exception as e:
                    log(f"place exc {str(e)[:80]}"); continue
                oid=getattr(r,"order_id",None) or getattr(r,"id",None); status=getattr(r,"status",None)
                if not oid:
                    log(f"  no oid (status={status} err={getattr(r,'error_msg',None)}) skip"); continue
                s.active={"slug":slug,"coin":w["coin"],"side":side,"B":B,"ask":ask,"bid":bid,"tok":tok,
                          "settle":w["settle"],"up":w["up"],"oid":oid,"filled":False,"conv":None}
                s.orders_done+=1
                log(f"PLACED #{s.orders_done} {slug} {side} {SHARES}sh @ {B} (ask={ask} maxLead={w['peak_lead']:.0f} lead={lead:+.0f}) oid={str(oid)[:14]}")
                break
        else:
            o=s.active
            w=s.win.get(o["slug"])
            # CANCEL on adverse trend while still unfilled (eebde's "pull the loser")
            if not o["filled"] and w and w["open"]:
                px=s.px.get(o["coin"])
                if px is not None:
                    lead=math.log(px/w["open"])*1e4; cur="Up" if lead>=0 else "Down"
                    if cur!=o["side"] or abs(lead)<THR_BPS*0.5:
                        try: cli.cancel_order(order_id=o["oid"]); log(f"  CANCEL(adverse) {o['slug']} lead now {lead:+.0f}bps (was {o['side']})")
                        except Exception as e: log(f"  cancel exc {str(e)[:50]}")
                        s.active=None; await asyncio.sleep(2); continue
            # poll fill
            try:
                od=cli.get_order(order_id=o["oid"]); mt=float(getattr(od,"size_matched",0) or 0)
                if mt>=SHARES-1e-6 and not o["filled"]:
                    o["filled"]=True; log(f"  *** FILLED {o['slug']} {SHARES}sh @ {o['B']} ***")
            except Exception as e: log(f"  poll exc {str(e)[:50]}")
            # settle: cancel if unfilled; else wait for ACTUAL on-chain resolution
            if o["settle"]-now()<-5:
                if not o["filled"]:
                    try: cli.cancel_order(order_id=o["oid"]); log(f"  unfilled -> CANCELED {o['slug']}")
                    except Exception as e: log(f"  cancel exc {str(e)[:50]}")
                    s.active=None
                else:
                    up_win=await resolve_up(o["up"], o["settle"])   # real outcome via Up-token prices-history
                    waited=now()-(o["settle"])
                    if up_win is None and waited<180:
                        await asyncio.sleep(5); continue   # not resolved yet, keep waiting (held position)
                    if up_win is None:
                        log(f"  {o['slug']} filled but UNRESOLVED after 180s — holding, manual check"); s.active=None
                    else:
                        won=(up_win and o["side"]=="Up") or ((not up_win) and o["side"]=="Down")
                        pnl=(1.0-o["B"])*SHARES if won else (-o["B"]*SHARES)
                        s.realized+=pnl; s.fills.append({"slug":o["slug"],"side":o["side"],"B":o["B"],"won":won,"pnl":round(pnl,2)})
                        open(OUTF,"a",encoding="utf-8").write(json.dumps({"slug":o["slug"],"coin":o["coin"],"side":o["side"],"B":o["B"],"ask":o["ask"],"filled":True,"won":won,"pnl":round(pnl,2)})+"\n")
                        try: wnow=float(cli.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6
                        except: wnow=None
                        wtxt=f" | WALLET=${wnow:.2f} (true Δ from start ${wnow-s.start_wallet:+.2f})" if wnow is not None else ""
                        log(f"  SETTLED {o['slug']} won={won} pnl=${pnl:+.2f} | cum computed=${s.realized:.2f}{wtxt}")
                        s.active=None
        await asyncio.sleep(2)
    try: wfin=float(cli.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6
    except: wfin=None
    wtxt=f" | WALLET ${s.start_wallet:.2f}->${wfin:.2f} (TRUE Δ ${wfin-s.start_wallet:+.2f})" if wfin is not None else ""
    log(f"FINAL: {s.orders_done} orders, {len(s.fills)} fills, computed ${s.realized:+.2f}{wtxt}")
    _run=False
async def main():
    s=St(); cli=trader()
    bal=float(cli.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6
    s.start_wallet=bal
    log(f"real_maker_test START wallet ${bal:.2f} | limits: {SHARES}sh x{MAX_ORDERS} orders, stop@${STOP_LOSS}, late>={LATE_FRAC}")
    await asyncio.gather(cb_ws(s),discovery(s),sampler(s),loop(s,cli))
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
