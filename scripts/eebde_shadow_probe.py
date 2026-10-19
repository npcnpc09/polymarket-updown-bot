"""eebde_shadow_probe.py — Shadow-trade eebde's decoded strategy live (OBSERVE ONLY).

Multi-coin: all 7 Polymarket updown coins (btc/eth/sol/xrp/bnb/doge/hype).
Tests whether WE can open the same position, same window, comparable time/price as
eebde — using the decoded signal: buy the coin-leading side late in the window.

Live streams, no orders:
  1. Binance futures WS  -> each coin's price + each window's open (kline at start).
  2. Polymarket CLOB WS  -> live ask of the leading side (what WE'd pay as taker).
  3. eebde data-api poll -> his actual trades on the same markets.

Output: data/eebde_shadow.jsonl (one row per settled signalled window; field 'asset').
"""
import argparse, asyncio, bisect, json, os, signal, sys, time
from collections import defaultdict
from datetime import datetime, timezone

import httpx
try:
    import websockets
except ImportError:
    print("pip install websockets"); sys.exit(1)

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except: pass

EEBDE = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
# coin -> Binance USDT-perp symbol (all verified present on fapi)
ASSETS = {"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT","xrp":"XRPUSDT",
          "bnb":"BNBUSDT","doge":"DOGEUSDT","hype":"HYPEUSDT"}
SYM2COIN = {v:k for k,v in ASSETS.items()}

MOVE_THR_BPS = 2.0
DECISION_TTL = 850   # fire EARLY (as soon as the coin leads by thr) to replicate eebde's early/cheap entry
MIN_TTL = 12

GAMMA = "https://gamma-api.polymarket.com/markets"
KLINE = "https://fapi.binance.com/fapi/v1/klines"
CLOB_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
DATA_API = "https://data-api.polymarket.com/activity"
def binance_ws_url():
    return "wss://fstream.binance.com/stream?streams="+"/".join(f"{s.lower()}@bookTicker" for s in ASSETS.values())

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); os.makedirs(DATA, exist_ok=True)
LOG = os.path.join(DATA, "eebde_late.log")
OUTF = os.path.join(DATA, "eebde_late.jsonl")

_run = True
def _sig(*_):
    global _run; _run = False
signal.signal(signal.SIGINT, _sig)

def now(): return time.time()
def iso(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def log(m):
    line = f"[{iso()}] {m}"; print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(line+"\n")
    except: pass


class OrderBook:
    def __init__(self): self.asks=[]
    def snap(self, asks):
        try: self.asks=sorted((float(a["price"]),float(a["size"])) for a in asks)
        except: pass
    def delta(self, ch):
        for c in ch:
            try: p=float(c["price"]); s=float(c["size"]); side=c.get("side","").upper()
            except: continue
            if side!="SELL": continue
            self.asks=[(pp,ss) for pp,ss in self.asks if abs(pp-p)>1e-9]
            if s>0: self.asks.append((p,s))
        self.asks.sort()
    def best_ask(self):
        for p,s in self.asks:
            if s>0 and p<1.0: return p
        return None


class S:
    def __init__(self):
        self.px=defaultdict(lambda: None)   # coin -> price
        self.pxE=defaultdict(lambda: None)  # coin -> binance event time (ms)
        self.books=defaultdict(OrderBook)
        self.win={}                   # slug -> {asset,sym,start,dur,settle,up_tok,dn_tok,open,cid}
        self.tok2={}
        self.tokens=[]; self.ver=0
        self.fired={}
        self.eebde=defaultdict(list)
        self.done=set()
        self.stats=defaultdict(int)


async def binance_ws(s):
    d=1
    while _run:
        try:
            async with websockets.connect(binance_ws_url(), ping_interval=15) as ws:
                log(f"binance WS connected ({len(ASSETS)} coins)"); d=1
                while _run:
                    m=json.loads(await asyncio.wait_for(ws.recv(),timeout=30))
                    dd=m.get("data",m); sym=dd.get("s"); coin=SYM2COIN.get(sym)
                    if not coin: continue
                    try:
                        s.px[coin]=(float(dd["b"])+float(dd["a"]))/2
                        s.pxE[coin]=dd.get("E") or dd.get("T")   # binance event time (ms)
                        s.stats["ticks"]+=1
                    except: pass
        except Exception as e:
            if not _run: break
            log(f"binance WS err {e}"); await asyncio.sleep(d); d=min(30,d*2)


async def fetch_open(c, sym, st):
    try:
        k=(await c.get(KLINE,params={"symbol":sym,"interval":"1m","startTime":st*1000,"limit":1})).json()
        if k: return float(k[0][1])
    except: pass
    return None


async def discovery(s):
    while _run:
        try:
            tnow=int(now())
            async with httpx.AsyncClient(timeout=15) as c:
                for asset,sym in ASSETS.items():
                    for mt,du in (("5m",300),("15m",900)):
                        base=(tnow//du)*du
                        for st in (base, base+du):
                            slug=f"{asset}-updown-{mt}-{st}"; settle=st+du; ttl=settle-now()
                            if ttl<MIN_TTL or ttl>du+60: continue
                            if slug in s.win: continue
                            try:
                                arr=(await c.get(GAMMA,params={"slug":slug})).json()
                                if not arr or arr[0].get("closed"): continue
                                m=arr[0]; ids=json.loads(m["clobTokenIds"]); outs=json.loads(m["outcomes"])
                                up=ids[outs.index("Up")]; dn=ids[outs.index("Down")]
                                op=await fetch_open(c,sym,st)
                                s.win[slug]={"asset":asset,"sym":sym,"start":st,"dur":du,"settle":settle,
                                             "up_tok":up,"dn_tok":dn,"open":op,"cid":m.get("conditionId")}
                            except Exception:
                                continue
                # retry missing opens
                for slug,w in list(s.win.items()):
                    if w["open"] is None and w["settle"]-now()>0:
                        w["open"]=await fetch_open(c,w["sym"],w["start"])
            # token subscription
            toks={}
            for slug,w in s.win.items():
                if w["settle"]-now()<-30: continue
                toks[w["up_tok"]]=(slug,"Up"); toks[w["dn_tok"]]=(slug,"Down")
            nt=sorted(toks)
            if nt!=s.tokens:
                s.tokens=nt; s.tok2=toks; s.ver+=1
            for slug in list(s.win.keys()):
                if s.win[slug]["settle"]-now()<-150 and slug not in s.fired:
                    del s.win[slug]
        except Exception as e:
            log(f"discovery err {e}")
        for _ in range(20):
            if not _run: break
            await asyncio.sleep(1)


async def clob_ws(s):
    d=1
    while _run:
        toks=list(s.tokens); ver=s.ver
        if not toks: await asyncio.sleep(1); continue
        try:
            async with websockets.connect(CLOB_WS, ping_interval=10, max_size=8*1024*1024) as ws:
                await ws.send(json.dumps({"type":"MARKET","assets_ids":toks}))
                d=1
                while _run and s.ver==ver:
                    try: raw=await asyncio.wait_for(ws.recv(),timeout=5)
                    except asyncio.TimeoutError: continue
                    for m in (lambda x: x if isinstance(x,list) else [x])(json.loads(raw)):
                        et=m.get("event_type") or m.get("type"); aid=m.get("asset_id") or m.get("market")
                        if not aid: continue
                        if et=="book": s.books[aid].snap(m.get("asks") or [])
                        elif et=="price_change": s.books[aid].delta(m.get("changes") or m.get("price_changes") or [m])
        except Exception as e:
            if not _run: break
            await asyncio.sleep(d); d=min(30,d*2)


async def eebde_poll(s):
    while _run:
        try:
            async with httpx.AsyncClient(timeout=12) as c:
                acts=(await c.get(DATA_API,params={"user":EEBDE,"limit":300})).json()
            live_cids={w["cid"] for w in s.win.values() if w["settle"]-now()>-30}
            for a in acts:
                if a.get("type")!="TRADE" or a.get("side")!="BUY": continue
                cid=a.get("conditionId")
                if cid not in live_cids: continue
                key=(cid,a.get("transactionHash"))
                if key in s.done: continue
                s.done.add(key)
                s.eebde[cid].append({"ts":a.get("timestamp"),"outcome":a.get("outcome"),
                                     "price":float(a.get("price",0)),"usd":float(a.get("usdcSize",0))})
        except Exception:
            pass
        for _ in range(5):
            if not _run: break
            await asyncio.sleep(1)


async def rest_ask(tok):
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok})).json()
        asks=sorted((float(a["price"]),float(a["size"])) for a in b.get("asks",[]))
        for p,sz in asks:
            if sz>0 and p<1.0: return p
    except: pass
    return None


async def signal_loop(s, args):
    while _run:
        for slug,w in list(s.win.items()):
            ttl=w["settle"]-now()
            px=s.px.get(w["asset"])
            if w["open"] is None or px is None: continue
            if slug not in s.fired and MIN_TTL<=ttl<=args.decision_ttl:
                dur=w["settle"]-w["start"]; elapsed=(now()-w["start"])/dur if dur>0 else 0
                move=(px/w["open"]-1)*1e4
                if elapsed>=args.late_frac and abs(move)>=args.thr:   # LATE: only fire in final (1-late_frac) of window (eebde loads late)
                    lead="Up" if move>=0 else "Down"
                    tok=w["up_tok"] if lead=="Up" else w["dn_tok"]
                    nowf=now()
                    tickE=s.pxE.get(w["asset"])
                    tick_age=round(nowf*1000-tickE) if tickE else None   # ms from binance tick to our fire
                    ask=s.books[tok].best_ask()
                    if ask is None: ask=await rest_ask(tok)
                    s.fired[slug]={"fire_ts":int(nowf),"fire_ms":round(nowf*1000),"tick_age_ms":tick_age,
                                   "ttl":int(ttl),"move_bps":round(move,1),
                                   "side":lead,"our_ask":ask,"open":w["open"],"px":px,"_final":False}
                    s.stats["fired"]+=1
                    log(f"SIGNAL {slug} ttl={int(ttl)}s move={move:+.1f}bps -> buy {lead} ask={ask}")
            if ttl<-20 and slug in s.fired and not s.fired[slug].get("_final"):
                await finalize(s, slug, w)
        await asyncio.sleep(1)


async def finalize(s, slug, w):
    fe=s.fired.get(slug)
    if not fe or fe.get("_final"): return
    fe["_final"]=True
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            k=(await c.get(KLINE,params={"symbol":w["sym"],"interval":"1m","startTime":(w["settle"]-60)*1000,"limit":2})).json()
        close=float(k[-1][4]) if k else None
    except: close=None
    winner=("Up" if close>=w["open"] else "Down") if close is not None else None
    our_win=(winner==fe["side"]) if winner else None
    ev=((1.0/fe["our_ask"]-1.0) if our_win else -1.0) if (our_win is not None and fe["our_ask"]) else None
    et=s.eebde.get(w["cid"],[]); eb=defaultdict(lambda:[0.0,0.0,10**11])
    for t in et:
        d=eb[t["outcome"]]; d[0]+=t["usd"]; d[1]+=t["price"]*t["usd"]; d[2]=min(d[2],t["ts"] or 10**11)
    ebs={o:{"usd":round(v[0],2),"avg_px":round(v[1]/v[0],3) if v[0] else None,"first_ts":v[2]} for o,v in eb.items()}
    el=ebs.get(fe["side"],{})
    td=(fe["fire_ts"]-el["first_ts"]) if el.get("first_ts") and el["first_ts"]<10**11 else None
    pd=(fe["our_ask"]-el["avg_px"]) if (fe.get("our_ask") and el.get("avg_px")) else None
    # timing alignment (his data is SECOND precision only): nearest his trade on our side to our fire
    fts=fe["fire_ts"]
    his_ts=[t["ts"] for t in et if t.get("outcome")==fe["side"] and t.get("ts")]
    nearest=min((abs(t-fts) for t in his_ts), default=None)
    row={"slug":slug,"asset":w["asset"],"fire_ttl":fe["ttl"],"move_bps":fe["move_bps"],"side":fe["side"],
         "our_ask":fe["our_ask"],"winner":winner,"our_win":our_win,"our_ev":round(ev,3) if ev is not None else None,
         "fire_ms":fe.get("fire_ms"),"tick_age_ms":fe.get("tick_age_ms"),
         "his_nearest_s":nearest,"his_within2s":sum(1 for t in his_ts if abs(t-fts)<=2),
         "his_within5s":sum(1 for t in his_ts if abs(t-fts)<=5),
         "eebde":ebs,"eebde_same_side":bool(el),"timing_delta_s":td,"price_delta":round(pd,3) if pd is not None else None}
    with open(OUTF,"a",encoding="utf-8") as f: f.write(json.dumps(row)+"\n")
    s.stats["settled"]+=1
    log(f"SETTLED {slug} ({w['asset']}) win={our_win} ev={row['our_ev']} same_side={row['eebde_same_side']} dt={td}s dp={row['price_delta']}")
    del s.win[slug]; del s.fired[slug]


async def reporter(s):
    await asyncio.sleep(20)
    while _run:
        opens=sum(1 for w in s.win.values() if w["open"] is not None)
        coins_live=len({w["asset"] for w in s.win.values()})
        log(f"  STAT ticks={s.stats['ticks']} coins_live={coins_live} windows={len(s.win)} opens_ok={opens} "
            f"fired={s.stats['fired']} settled={s.stats['settled']} eebde_mkts={len(s.eebde)}")
        for _ in range(30):
            if not _run: break
            await asyncio.sleep(1)


async def main(args):
    s=S()
    log(f"eebde_shadow_probe MULTI-COIN {list(ASSETS)} — OBSERVE ONLY | thr={args.thr}bps decision_ttl={args.decision_ttl}s")
    await asyncio.gather(binance_ws(s),discovery(s),clob_ws(s),eebde_poll(s),signal_loop(s,args),reporter(s))


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--thr",type=float,default=MOVE_THR_BPS)
    ap.add_argument("--decision-ttl",type=float,default=DECISION_TTL)
    ap.add_argument("--late-frac",type=float,default=0.80,help="only fire after this fraction of window elapsed (eebde loads late)")
    a=ap.parse_args()
    try: asyncio.run(main(a))
    except KeyboardInterrupt: pass
