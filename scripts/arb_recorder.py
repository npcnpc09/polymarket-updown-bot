"""arb_recorder.py — record real BTC 5m order-book + trade stream for offline arb sim.

Captures everything needed to realistically simulate our maker bids filling against real
taker flow: book snapshots, price_change deltas, and last_trade_price (trade prints).
Each line is a raw CLOB WS message + rx timestamp. Plus per-window metadata (tokens, start)
for settlement. NO orders, NO money.

Output: data/recordings/rec_<startts>.jsonl   (events)
        data/recordings/windows_<startts>.jsonl (window metadata)
"""
import asyncio, json, os, signal, sys, time
from datetime import datetime, timezone
import httpx
try: import websockets
except ImportError: print("pip install websockets"); sys.exit(1)
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except: pass

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECDIR=os.path.join(ROOT,"data","recordings"); os.makedirs(RECDIR,exist_ok=True)
GAMMA="https://gamma-api.polymarket.com/markets"
CLOB_WS="wss://ws-subscriptions-clob.polymarket.com/ws/market"
ASSET="btc"; REFRESH=30

_run=True
def _sig(*_):
    global _run; _run=False
signal.signal(signal.SIGINT,_sig)
def now(): return time.time()
def iso(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def log(m): print(f"[{iso()}] {m}", flush=True)

class S:
    def __init__(self, rid):
        self.evf=open(os.path.join(RECDIR,f"rec_{rid}.jsonl"),"a",encoding="utf-8")
        self.winf=open(os.path.join(RECDIR,f"windows_{rid}.jsonl"),"a",encoding="utf-8")
        self.win={}; self.tok2={}; self.tokens=[]; self.ver=0; self.n=0; self.logged=set()

async def discovery(s):
    while _run:
        try:
            tnow=int(now())
            async with httpx.AsyncClient(timeout=15) as c:
                for off in (0,300,600):
                    st=(tnow//300)*300+off; slug=f"{ASSET}-updown-5m-{st}"
                    if slug in s.win: continue
                    if st+300-now()<10 or st+300-now()>660: continue
                    try:
                        arr=(await c.get(GAMMA,params={"slug":slug})).json()
                        if not arr or arr[0].get("closed"): continue
                        m=arr[0]; ids=json.loads(m["clobTokenIds"]); outs=json.loads(m["outcomes"])
                        up=ids[outs.index("Up")]; dn=ids[outs.index("Down")]
                        s.win[slug]={"slug":slug,"start":st,"settle":st+300,"up":up,"dn":dn,"cid":m.get("conditionId")}
                        if slug not in s.logged:
                            s.winf.write(json.dumps(s.win[slug])+"\n"); s.winf.flush(); s.logged.add(slug)
                    except: pass
            toks={}
            for slug,w in s.win.items():
                if w["settle"]-now()<-30: continue
                toks[w["up"]]=slug; toks[w["dn"]]=slug
            nt=sorted(toks)
            if nt!=s.tokens: s.tokens=nt; s.tok2=toks; s.ver+=1
            for slug in list(s.win.keys()):
                if s.win[slug]["settle"]-now()<-120: del s.win[slug]
        except Exception as e: log(f"disc err {e}")
        for _ in range(REFRESH):
            if not _run: break
            await asyncio.sleep(1)

async def ws_loop(s):
    d=1
    while _run:
        toks=list(s.tokens); ver=s.ver
        if not toks: await asyncio.sleep(1); continue
        try:
            async with websockets.connect(CLOB_WS,ping_interval=10,max_size=8*1024*1024) as ws:
                await ws.send(json.dumps({"type":"MARKET","assets_ids":toks}))
                log(f"recording {len(toks)} tokens (ver {ver})"); d=1
                while _run and s.ver==ver:
                    try: raw=await asyncio.wait_for(ws.recv(),timeout=5)
                    except asyncio.TimeoutError: continue
                    rx=now()
                    try: msg=json.loads(raw)
                    except: continue
                    for m in (msg if isinstance(msg,list) else [msg]):
                        et=m.get("event_type") or m.get("type"); aid=m.get("asset_id") or m.get("market")
                        if not aid: continue
                        s.evf.write(json.dumps({"rx":round(rx,3),"et":et,"aid":aid,"m":m})+"\n"); s.n+=1
                        if s.n%2000==0: s.evf.flush(); log(f"  recorded {s.n} events, windows={len(s.win)}")
        except Exception as e:
            if not _run: break
            log(f"ws err {e}; retry {d}s"); await asyncio.sleep(d); d=min(30,d*2)

async def main():
    rid=int(now())
    s=S(rid)
    log(f"arb_recorder started -> rec_{rid}.jsonl (BTC 5m, observe-only)")
    try:
        await asyncio.gather(discovery(s),ws_loop(s))
    finally:
        s.evf.flush(); s.evf.close(); s.winf.close()
        log(f"stopped. total events={s.n}")

if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
