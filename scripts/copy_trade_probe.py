"""copy_trade_probe.py — OBSERVE-ONLY. Paper copy-trade eebde. Poll his live BUY trades;
when he buys a side on a live updown market, snapshot OUR taker cost (current best ask of
that side = what we'd pay copying him) + his price/size/ttl. At settle, resolve (Binance
close vs open) and compute OUR copy EV at the ask. Segment by his conviction (size, his
price, ttl) to find the subset where copying is +EV. NO money. Row -> data/copy_trade.jsonl
"""
import asyncio, json, time, signal, sys, math, datetime, re
from collections import defaultdict
import httpx
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
EEBDE="0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
DATA_API="https://data-api.polymarket.com/activity"
GAMMA="https://gamma-api.polymarket.com/markets"
KLINE="https://api.binance.com/api/v3/klines"
SYM={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT","xrp":"XRPUSDT","doge":"DOGEUSDT"}
MIN_SIZE=20.0   # only copy his conviction trades (>= $20)
OUTF="data/copy_trade.jsonl"; LOG="data/copy_trade.log"
_run=True
def _sig(*_):
    global _run; _run=False
signal.signal(signal.SIGINT,_sig)
def now(): return time.time()
def log(m):
    line=f"[{datetime.datetime.utcnow().strftime('%H:%M:%S')}] {m}"; print(line,flush=True)
    try: open(LOG,"a",encoding="utf-8").write(line+"\n")
    except: pass
class S:
    def __init__(s): s.watch={}; s.seen=set(); s.win={}; s.stats=defaultdict(int)
def parse(slug):
    m=re.match(r"(\w+)-updown-(5m|15m)-(\d+)",slug or "")
    if not m or m.group(1) not in SYM: return None
    return m.group(1),(300 if m.group(2)=="5m" else 900),int(m.group(3))
async def book_ask(c,tok):
    try:
        b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok})).json()
        asks=sorted(float(a["price"]) for a in b.get("asks",[]) if float(a["size"])>0 and float(a["price"])<1)
        bids=sorted((float(a["price"]) for a in b.get("bids",[]) if float(a["size"])>0 and float(a["price"])>0),reverse=True)
        return (asks[0] if asks else None),(bids[0] if bids else None)
    except: return None,None
async def poller(s):
    while _run:
        try:
            async with httpx.AsyncClient(timeout=12) as c:
                acts=(await c.get(DATA_API,params={"user":EEBDE,"limit":200})).json()
                for a in acts:
                    if a.get("type")!="TRADE" or a.get("side")!="BUY": continue
                    pm=parse(a.get("slug",""))
                    if not pm: continue
                    coin,dur,st=pm; settle=st+dur; ttl=settle-now()
                    if ttl<8: continue                                  # too late to copy
                    if float(a.get("usdcSize",0))<MIN_SIZE: continue    # conviction only
                    key=(a.get("conditionId"),a.get("outcome"))
                    if key in s.seen: continue                          # one snapshot per market+side
                    ids=None
                    try:
                        arr=(await c.get(GAMMA,params={"slug":a["slug"]})).json()
                        if arr: ids=json.loads(arr[0]["clobTokenIds"]); outs=json.loads(arr[0]["outcomes"])
                    except: pass
                    if not ids: continue                                # transient gamma fail -> retry next poll (DON'T blacklist)
                    tok=ids[outs.index(a["outcome"])]
                    our_ask,our_bid=await book_ask(c,tok)
                    if our_ask is None: continue                        # transient book fail -> retry next poll
                    s.seen.add(key)                                     # only mark seen AFTER a successful capture
                    s.watch[key]={"coin":coin,"slug":a["slug"],"side":a["outcome"],"settle":settle,
                        "his_price":float(a.get("price",0)),"his_size":float(a.get("usdcSize",0)),
                        "our_ask":our_ask,"ttl":int(ttl),"st":st,"dur":dur,"sym":SYM[coin]}
                    s.stats["watched"]+=1
                    log(f"COPY-WATCH {a['slug']} {a['outcome']} his_px={a.get('price')} his_$={round(float(a.get('usdcSize',0)))} our_ask={our_ask} ttl={int(ttl)}s")
        except Exception as e: log(f"poll {str(e)[:40]}")
        for _ in range(4):
            if not _run: break
            await asyncio.sleep(1)
async def settler(s):
    await asyncio.sleep(10)
    while _run:
        async with httpx.AsyncClient(timeout=12) as c:
            for key,w in list(s.watch.items()):
                if w["settle"]-now()>5: continue
                try:
                    k=(await c.get(KLINE,params={"symbol":w["sym"],"interval":"1m","startTime":(w["st"])*1000,"endTime":(w["st"]+90)*1000,"limit":2})).json()
                    op=float(k[0][1]) if k else None
                    k2=(await c.get(KLINE,params={"symbol":w["sym"],"interval":"1m","startTime":(w["settle"]-60)*1000,"limit":2})).json()
                    cl=float(k2[-1][4]) if k2 else None
                except: op=cl=None
                if op is None or cl is None:
                    if w["settle"]-now()<-120: del s.watch[key]
                    continue
                winner="Up" if cl>=op else "Down"; win=(winner==w["side"])
                ev=(1.0/w["our_ask"]-1.0) if win else -1.0
                row={"slug":w["slug"],"coin":w["coin"],"side":w["side"],"his_price":w["his_price"],
                     "his_size":round(w["his_size"]),"our_ask":w["our_ask"],"ttl":w["ttl"],
                     "win":win,"copy_ev":round(ev,3)}
                open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
                s.stats["settled"]+=1
                log(f"SETTLED {w['slug']} {w['side']} our_ask={w['our_ask']} win={win} copy_ev={round(ev,3)}")
                del s.watch[key]
        for _ in range(3):
            if not _run: break
            await asyncio.sleep(1)
async def reporter(s):
    await asyncio.sleep(20)
    while _run:
        rows=[]
        try:
            for ln in open(OUTF,encoding="utf-8"): rows.append(json.loads(ln))
        except: pass
        if rows:
            def agg(rs,lab):
                if not rs: return
                wr=sum(1 for r in rs if r["win"])/len(rs)*100; ev=sum(r["copy_ev"] for r in rs)/len(rs)*100
                ak=sum(r["our_ask"] for r in rs)/len(rs)
                log(f"   {lab}: n={len(rs)} WR={wr:.0f}% our_ask={ak:.2f} copy_EV={ev:+.1f}%")
            log(f"STAT watched={s.stats['watched']} settled={len(rows)}")
            agg(rows,"ALL")
            agg([r for r in rows if r["his_price"]>=0.85],"his_px>=0.85 (his high-conviction)")
            agg([r for r in rows if r["his_size"]>=100],"his_$>=100 (big bets)")
            agg([r for r in rows if r["ttl"]<=60],"ttl<=60s (late/locked)")
        else:
            log(f"STAT watched={s.stats['watched']} settled=0")
        for _ in range(30):
            if not _run: break
            await asyncio.sleep(1)
async def main():
    s=S(); log(f"copy_trade_probe OBSERVE-ONLY paper-copy eebde (conviction>=${MIN_SIZE}) taker @ our ask")
    await asyncio.gather(poller(s),settler(s),reporter(s))
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
