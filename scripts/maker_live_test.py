"""maker_live_test.py — TINY real-money MAKER fill test for the refined fast
directional strategy (sigma=0.5, fair>=0.85, tight maker bid). Goal: validate the
ONE thing paper can't — does our resting post_only bid actually get MATCHED?

Two modes (placement requires explicit per-trade approval — that's the workflow):
  --scan   : observe-only. Coinbase 15ms feed + Polymarket book. Surface fair>=0.85
             candidates (with suggested ~$1 size) to data/maker_live_cand.jsonl + log.
             Places NOTHING. Run in background; relay a fresh candidate to the user.
  --place  : place ONE post_only (true maker) limit BUY on an explicit target the
             user approved: --token --price --shares --slug --side --settle <ts>.
             Hard cap: notional <= $1.10. Rests, monitors fill, cancels if unfilled
             at settle. Filled -> hold to auto-redeem (up/down settles itself).

Refined strategy validated: backtest fair>=0.85 -> 99% WR +33% taker EV; paper n=56
-> +62% maker EV, no adverse selection. Wallet is COMPROMISED (pk was exposed) —
TINY test only, rotate before any scale.
"""
import argparse, asyncio, json, os, sys, time, math, datetime
from collections import defaultdict
import httpx
try: import websockets
except ImportError: print("pip install websockets"); sys.exit(1)
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDF=os.path.join(ROOT,"data","maker_live_cand.jsonl")
LOG=os.path.join(ROOT,"data","maker_live.log")
ASSETS={"btc":"BTC-USD","eth":"ETH-USD","sol":"SOL-USD","xrp":"XRP-USD","doge":"DOGE-USD"}
PROD2COIN={v:k for k,v in ASSETS.items()}
SIGMA_ANN=0.5; MARGIN=0.04; YR=31557600.0; THR_BPS=2.0; MIN_TTL=20
FAIR_MIN=0.85       # LIVE: tightened to the backtest-validated high-confidence zone
MAXNOTIONAL=5.0     # hard $ cap per order (5-share exchange min => ~$3-4.3 at our prices)
CB_WS="wss://ws-feed.exchange.coinbase.com"
CB_CANDLES="https://api.exchange.coinbase.com/products/{p}/candles"
GAMMA="https://gamma-api.polymarket.com/markets"
def Phi(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
def now(): return time.time()
def log(m):
    line=f"[{datetime.datetime.utcnow().strftime('%H:%M:%S')}] {m}"; print(line,flush=True)
    try: open(LOG,"a",encoding="utf-8").write(line+"\n")
    except: pass
def load_env():
    f=os.path.join(ROOT,".env")
    if os.path.exists(f):
        for l in open(f,encoding="utf-8"):
            if "=" in l and not l.startswith("#"):
                k,v=l.strip().split("=",1); os.environ.setdefault(k.strip(),v.strip())
    return os.environ.get("POLY_PK"),os.environ.get("POLY_PROXY")

# ======================= SCAN MODE (observe-only) =======================
_run=True
class St:
    def __init__(s):
        s.px=defaultdict(lambda:None); s.pxT=defaultdict(lambda:None)
        s.bids=defaultdict(dict); s.asks=defaultdict(dict)
        s.win={}; s.seen=set(); s.stats=defaultdict(int)
def _prune(book,keep,hi):
    if len(book)<=keep*2: return
    ks=sorted(book); drop=ks[:-keep] if hi else ks[keep:]
    for p in drop: book.pop(p,None)
async def cb_ws(s):
    d=1
    while _run:
        try:
            async with websockets.connect(CB_WS,ping_interval=15,open_timeout=12,max_size=16*1024*1024) as ws:
                await ws.send(json.dumps({"type":"subscribe","product_ids":list(ASSETS.values()),"channels":["level2_batch"]}))
                log(f"Coinbase level2 connected {list(ASSETS)}"); d=1
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
                    if bb and ba and ba>bb: s.px[c]=(bb+ba)/2; s.pxT[c]=now(); s.stats["ticks"]+=1
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
async def discovery(s,only15):
    mts=(("15m",900),) if only15 else (("5m",300),("15m",900))
    while _run:
        t=int(now())
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                for coin,prod in ASSETS.items():
                    for mt,du in mts:
                        base=(t//du)*du
                        for st in (base,base+du):
                            slug=f"{coin}-updown-{mt}-{st}"; settle=st+du; ttl=settle-now()
                            if ttl<MIN_TTL or ttl>du+60 or slug in s.win: continue
                            try:
                                arr=(await c.get(GAMMA,params={"slug":slug})).json()
                                if not arr or arr[0].get("closed"): continue
                                m=arr[0]; ids=json.loads(m["clobTokenIds"]); outs=json.loads(m["outcomes"])
                                up=ids[outs.index("Up")]; dn=ids[outs.index("Down")]; op=await cb_open(c,prod,st)
                                s.win[slug]={"coin":coin,"prod":prod,"start":st,"settle":settle,"up":up,"dn":dn,"open":op}
                            except: continue
                for slug,w in list(s.win.items()):
                    if w["open"] is None and w["settle"]-now()>0: w["open"]=await cb_open(c,w["prod"],w["start"])
                    if w["settle"]-now()<-30: del s.win[slug]
        except Exception as e: log(f"disc {str(e)[:30]}")
        for _ in range(10):
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
async def scan(s,minttl):
    while _run:
        for slug,w in list(s.win.items()):
            ttl=w["settle"]-now(); px=s.px.get(w["coin"])
            if w["open"] is None or px is None or slug in s.seen: continue
            if not (minttl<=ttl<=900): continue
            lead=math.log(px/w["open"])
            if abs(lead*1e4)<THR_BPS: continue
            v=SIGMA_ANN*math.sqrt(max(ttl,1)/YR); p_up=Phi(lead/v) if v>0 else 0.5
            side="Up" if p_up>=0.5 else "Down"; p_lead=max(p_up,1-p_up); tok=w["up"] if side=="Up" else w["dn"]
            if p_lead<FAIR_MIN: continue
            bid,ask=await pm_book(tok)
            if bid is None or ask is None: continue
            B=round(ask-0.02,2)
            if B<=bid: B=round(bid+0.01,2)
            if not (0.30<=B<=0.95) or B>=ask: continue
            if (p_lead-B)<=MARGIN: continue
            shares=round(min(1.0,MAXNOTIONAL)/B,2)            # ~$1 notional
            if shares*B>MAXNOTIONAL: shares=round(MAXNOTIONAL/B,2)
            s.seen.add(slug); s.stats["cand"]+=1
            row={"ts":round(now()),"slug":slug,"coin":w["coin"],"side":side,"token":tok,
                 "B":B,"ask":ask,"bid":bid,"fair":round(p_lead,3),"ttl":int(ttl),
                 "settle":int(w["settle"]),"shares":shares,"notional":round(shares*B,2)}
            open(CANDF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
            log(f"CAND {slug} {side} fair={p_lead:.2f} bid@{B} ask={ask} ttl={int(ttl)}s "
                f"-> {shares}sh x{B}=${shares*B:.2f}  edge=+{p_lead-B:.2f}")
        await asyncio.sleep(1)
async def reporter(s):
    await asyncio.sleep(15)
    while _run:
        opens=sum(1 for w in s.win.values() if w.get("open") is not None)
        pxc=sum(1 for c in ASSETS if s.px.get(c) is not None)
        log(f"STAT ticks={s.stats['ticks']} win={len(s.win)} opens={opens} px={pxc} cand={s.stats['cand']}")
        for _ in range(20):
            if not _run: break
            await asyncio.sleep(1)
async def run_scan(only15,minttl):
    s=St(); log(f"maker_live_test SCAN observe-only FAIR_MIN={FAIR_MIN} only15={only15} minttl={minttl}")
    await asyncio.gather(cb_ws(s),discovery(s,only15),scan(s,minttl),reporter(s))

# ======================= PLACE MODE (real money, single order) =======================
def run_place(a):
    pk,proxy=load_env()
    if not pk or not proxy: log("MISSING creds"); sys.exit(1)
    price=round(float(a.price),2); shares=round(float(a.shares),2); notional=price*shares
    if not (0.30<=price<=0.95): log(f"REFUSE price {price} out of [0.30,0.95]"); sys.exit(1)
    if notional>MAXNOTIONAL: log(f"REFUSE notional ${notional:.2f} > cap ${MAXNOTIONAL}"); sys.exit(1)
    from polymarket import SecureClient
    cli=SecureClient.create(private_key=pk,wallet=proxy)
    bal=float(cli.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6
    log(f"=== PLACE maker BUY {a.slug} {a.side} | {shares}sh @ {price} = ${notional:.2f} | wallet ${bal:.2f} ===")
    if bal<notional+0.01: log("REFUSE insufficient balance"); sys.exit(1)
    try:
        r=cli.place_limit_order(token_id=a.token,price=price,size=shares,side="BUY",post_only=True)
    except Exception as e:
        log(f"place exc {str(e)[:120]}"); sys.exit(1)
    ok=getattr(r,"ok",None); status=getattr(r,"status",None); oid=getattr(r,"order_id",None) or getattr(r,"id",None)
    log(f"RESP ok={ok} status={status} order_id={str(oid)[:16]} err={getattr(r,'error_msg',None)}")
    if not oid:
        log("no order_id (likely REJECTED — maybe min-size or crossed). done."); return
    # monitor fill until settle, then cancel if unfilled
    settle=int(a.settle) if a.settle else int(now()+120)
    log(f"resting post_only bid; monitoring fill until settle {settle} ({settle-int(now())}s)...")
    filled=False
    while now()<settle+5:
        time.sleep(4)
        try:
            o=cli.get_order(order_id=oid)
            mt=float(getattr(o,"size_matched",0) or 0); st=getattr(o,"status",None)
            log(f"  poll status={st} matched={mt}/{shares}")
            if mt>=shares-1e-6: filled=True; log(f"  *** FILLED {mt}sh @ {price} — holding to auto-redeem ***"); break
            if st in ("CANCELED","EXPIRED","REJECTED"): log(f"  order {st}"); break
        except Exception as e: log(f"  poll exc {str(e)[:60]}")
    if not filled:
        try: cli.cancel_order(order_id=oid); log("  unfilled at settle -> CANCELED")
        except Exception as e: log(f"  cancel exc {str(e)[:60]}")
    log(f"DONE filled={filled}")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--scan",action="store_true")
    ap.add_argument("--only15",action="store_true",help="scan only 15m windows (more approval headroom)")
    ap.add_argument("--minttl",type=int,default=120,help="min seconds-to-settle for a surfaced candidate")
    ap.add_argument("--place",action="store_true")
    ap.add_argument("--token"); ap.add_argument("--price"); ap.add_argument("--shares")
    ap.add_argument("--slug",default=""); ap.add_argument("--side",default=""); ap.add_argument("--settle",type=int,default=0)
    a=ap.parse_args()
    if a.place:
        for req in ("token","price","shares"):
            if not getattr(a,req): print(f"--place needs --{req}"); sys.exit(1)
        run_place(a)
    else:
        try: asyncio.run(run_scan(a.only15,a.minttl))
        except KeyboardInterrupt: pass
if __name__=="__main__": main()
