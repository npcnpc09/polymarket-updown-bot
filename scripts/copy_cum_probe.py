"""copy_cum_probe.py — copy eebde's CUMULATIVE favorite load (validates/trades the $1000+ favorite bucket;
hist $1k-3k = 89% win / +12c edge). Tracks his running $ per (window,side) across polls (dedup by tx).
When the FAVORITE side's cumulative first crosses COPY_MIN ($1000), snapshot our taker ask (DRY) OR
place a REAL tiny taker order (--place). At settle resolve (binance close vs open = Chainlink at >=5bps).

  DRY  (default)  : OBSERVE ONLY -> data/copy_cum.jsonl
  --place         : REAL money, HARD CAPS below, -> data/copy_cum_live.jsonl
Wallet 0x149200 is COMPROMISED (pk exposed) — tiny only. Agent-initiated real orders are permission-gated;
the USER must authorize (I cannot self-add an allow-rule). This bot is NOT in the watchdog (won't auto-restart)."""
import asyncio, json, time, signal, sys, os, math, datetime, re
from collections import defaultdict
import httpx
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACE=("--place" in sys.argv)
EEBDE="0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
DATA_API="https://data-api.polymarket.com/activity"
GAMMA="https://gamma-api.polymarket.com/markets"
KLINE="https://api.binance.com/api/v3/klines"
SYM={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT","xrp":"XRPUSDT","doge":"DOGEUSDT"}
LEAD_MIN=5.0      # ADDED 2026-06-06: only copy if the UNDERLYING (binance) leads his favorite side by
                  # >= this (bps) at copy time. Validated on BOTH backtest (+0.18 EV) AND live OOS (102
                  # trades: lead>=5 = 92% win/+0.24 EV; lead<0 = 33% win/-1.28 — the disaster trades).
                  # Cuts windows where price doesn't confirm his favorite (contested/weak = the loss cluster).
COPY_MIN=1000.0   # REVERTED 2026-06-06 back to 1000. $300 FAILED LIVE (OOS): n=15 53% win / -$9.1 / EV -0.60
                  # vs $1000 85% / +$3.2. Backtest said $300 +EV but in the live CHOPPY regime, the early/
                  # less-confirmed $300 entries get chopped (favorite not yet established). Confirmation >
                  # cheapness in chop. Classic in-sample(backtest)-looks-good / OOS(live)-fails again.
# ---- HARD RISK CAPS (--place only); wallet compromised -> tiny ----
SHARES=5; MAX_CONCURRENT=3; MAX_PER_COIN=2; MAX_TOTAL_ORDERS=40; STOP_LOSS=-15.0; MAXNOTIONAL=5.0
_sfx="_live" if PLACE else ""
OUTF=os.path.join(ROOT,"data",f"copy_cum{_sfx}.jsonl"); LOG=os.path.join(ROOT,"data",f"copy_cum{_sfx}.log")
_run=True
def _sig(*_):
    global _run; _run=False
signal.signal(signal.SIGINT,_sig)
def now(): return time.time()
def log(m):
    line=f"[{datetime.datetime.utcnow().strftime('%H:%M:%S')}] {m}"; print(line,flush=True)
    try: open(LOG,"a",encoding="utf-8").write(line+"\n")
    except: pass
def parse(slug):
    m=re.match(r"(\w+)-updown-(5m|15m)-(\d+)",slug or "")
    if not m or m.group(1) not in SYM: return None
    return m.group(1),(300 if m.group(2)=="5m" else 900),int(m.group(3))
def load_env():
    for l in open(os.path.join(ROOT,".env"),encoding="utf-8"):
        if "=" in l and not l.startswith("#"):
            k,v=l.strip().split("=",1); os.environ.setdefault(k.strip(),v.strip())
    return os.environ["POLY_PK"],os.environ["POLY_PROXY"]
def trader():
    pk,proxy=load_env()
    from polymarket import SecureClient
    return SecureClient.create(private_key=pk,wallet=proxy)
class S:
    def __init__(s):
        s.cum=defaultdict(lambda:{"val":0.0,"pxsz":0.0,"sz":0.0})
        s.seen_tx=set(); s.copied={}; s.done=set(); s.stats=defaultdict(int)
        s.realized=0.0; s.orders_done=0; s.halted=False; s.neg_logged=set()
async def book_ask(c,tok):
    try:
        b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok})).json()
        asks=sorted(float(a["price"]) for a in b.get("asks",[]) if float(a["size"])>0 and float(a["price"])<1)
        return asks[0] if asks else None
    except: return None
async def lead_toward(c,sym,st,side):
    """underlying lead (bps) toward `side` now vs window open. >0 = price confirming his favorite side."""
    try:
        k=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":st*1000,"limit":1},timeout=8)).json()
        op=float(k[0][1])
        tp=(await c.get("https://api.binance.com/api/v3/ticker/price",params={"symbol":sym},timeout=8)).json()
        lead=math.log(float(tp["price"])/op)*1e4
        return lead if side=="Up" else -lead
    except: return None
async def token_id(c,slug,outcome):
    try:
        arr=(await c.get(GAMMA,params={"slug":slug})).json()
        if arr:
            ids=json.loads(arr[0]["clobTokenIds"]); outs=json.loads(arr[0]["outcomes"])
            return ids[outs.index(outcome)]
    except: pass
    return None
async def poller(s,cli):
    while _run:
        try:
            async with httpx.AsyncClient(timeout=12) as c:
                acts=(await c.get(DATA_API,params={"user":EEBDE,"limit":500})).json()
                for a in acts:
                    if a.get("type")!="TRADE" or a.get("side")!="BUY": continue
                    pm=parse(a.get("slug",""))
                    if not pm: continue
                    coin,dur,st=pm; settle=st+dur; ttl=settle-now()
                    cond=a.get("conditionId"); outc=a.get("outcome")
                    if outc not in ("Up","Down"): continue
                    txk=(a.get("transactionHash"),outc,a.get("size"),a.get("timestamp"))
                    if txk in s.seen_tx: continue
                    s.seen_tx.add(txk)
                    p=float(a.get("price",0) or 0); usz=float(a.get("usdcSize",0) or 0); sh=float(a.get("size",0) or 0)
                    k=(cond,outc); e=s.cum[k]; e["val"]+=usz; e["pxsz"]+=p*sh; e["sz"]+=sh
                    if ttl<8 or k in s.copied or k in s.done: continue
                    other=s.cum.get((cond,"Up" if outc=="Down" else "Down"),{"val":0.0})
                    if e["val"]<COPY_MIN or e["val"]<other["val"]: continue
                    # ---- copy trigger: favorite cumulative crossed COPY_MIN ----
                    if PLACE:
                        if s.halted or s.orders_done>=MAX_TOTAL_ORDERS: continue
                        if s.realized<=STOP_LOSS:
                            if not s.halted: log(f"=== STOP-LOSS ${s.realized:.2f}<= ${STOP_LOSS} — HALT new orders ==="); s.halted=True
                            continue
                        liveN=sum(1 for v in s.copied.values() if not v.get("settled"))
                        if liveN>=MAX_CONCURRENT: continue
                        if sum(1 for v in s.copied.values() if not v.get("settled") and v["coin"]==coin)>=MAX_PER_COIN: continue
                    tok=await token_id(c,a["slug"],outc)
                    if not tok: continue
                    ask=await book_ask(c,tok)
                    if ask is None or not (0.30<=ask<=0.95) or ask*SHARES>MAXNOTIONAL: continue
                    avgpx=e["pxsz"]/e["sz"] if e["sz"]>0 else 0
                    # NEG-SLIPPAGE FILTER (--place only): if our ask < his accumulation avg, the favorite has
                    # FADED since he loaded -> we'd be buying a reversing favorite (the loss cluster, n=22:
                    # pos-slip 15/15 win, neg-slip 3/6). Skip; re-evaluates next poll if it recovers. Observe keeps all.
                    if PLACE and ask < avgpx-0.08:   # only skip BIG negative slippage (>8c below his avg);
                        if k not in s.neg_logged:      # tightened from <avgpx (cut 3 wins) to <avgpx-0.08 (cuts 1)
                            log(f"  SKIP big-neg-slip {a['slug']} {outc} our_ask={ask} < his_avg-0.08={round(avgpx-0.08,3)} (faded favorite)")
                            s.neg_logged.add(k)
                        continue
                    # LEAD FILTER (--place only): underlying must lead his favorite by >= LEAD_MIN bps
                    # (price confirms direction). Backtest +0.18 / live OOS +0.24; lead<0 = 33% win disaster.
                    leadf=await lead_toward(c,SYM[coin],st,outc)
                    if PLACE and (leadf is None or leadf<LEAD_MIN):
                        if k not in s.neg_logged:
                            log(f"  SKIP lead<{LEAD_MIN:.0f} {a['slug']} {outc} leadf={round(leadf,1) if leadf is not None else None}")
                            s.neg_logged.add(k)
                        continue
                    rec={"coin":coin,"slug":a["slug"],"side":outc,"settle":settle,"st":st,"dur":dur,"sym":SYM[coin],
                         "our_ask":ask,"ttl":int(ttl),"cum_at_copy":round(e["val"]),"avgpx":round(avgpx,3),"leadf":round(leadf,1),"oid":None,"settled":False}
                    if PLACE:
                        B=round(ask,2)
                        try:
                            r=cli.place_limit_order(token_id=tok,price=B,size=SHARES,side="BUY",post_only=False)
                            oid=getattr(r,"order_id",None) or getattr(r,"id",None)
                        except Exception as ex:
                            log(f"  PLACE-BLOCKED/err {a['slug']} {outc}: {str(ex)[:90]}"); continue
                        if not oid:
                            log(f"  no oid {a['slug']} status={getattr(r,'status',None)} err={getattr(r,'error_msg',None)}"); continue
                        rec["oid"]=oid; rec["our_ask"]=B
                        s.orders_done+=1
                        log(f"*** LIVE-COPY #{s.orders_done} {a['slug']} {outc} {SHARES}sh @ {B} hisCum=${round(e['val'])} ttl={int(ttl)}s oid={str(oid)[:12]} ***")
                    else:
                        log(f"CUM-COPY {a['slug']} {outc} hisCum=${round(e['val'])} avgpx={round(avgpx,2)} our_ask={ask} ttl={int(ttl)}s")
                    s.copied[k]=rec; s.stats["copied"]+=1
        except Exception as e: log(f"poll {str(e)[:60]}")
        for _ in range(3):
            if not _run: break
            await asyncio.sleep(1)
async def settler(s,cli):
    await asyncio.sleep(10)
    while _run:
        async with httpx.AsyncClient(timeout=12) as c:
            for k,w in list(s.copied.items()):
                if w.get("settled") or w["settle"]-now()>5: continue
                try:
                    k1=(await c.get(KLINE,params={"symbol":w["sym"],"interval":"1m","startTime":w["st"]*1000,"endTime":(w["st"]+90)*1000,"limit":2})).json()
                    op=float(k1[0][1]) if k1 else None
                    k2=(await c.get(KLINE,params={"symbol":w["sym"],"interval":"1m","startTime":(w["settle"]-60)*1000,"limit":2})).json()
                    cl=float(k2[-1][4]) if k2 else None
                except: op=cl=None
                if op is None or cl is None:
                    if w["settle"]-now()<-180: w["settled"]=True; s.done.add(k); s.copied.pop(k,None)
                    continue
                win=(("Up" if cl>=op else "Down")==w["side"])
                pnl=(1.0-w["our_ask"])*SHARES if win else (-w["our_ask"]*SHARES)
                ev=(1.0/w["our_ask"]-1.0) if win else -1.0
                final_cum=round(s.cum.get(k,{"val":0})["val"])
                row={"slug":w["slug"],"coin":w["coin"],"side":w["side"],"his_avgpx":w["avgpx"],"our_ask":w["our_ask"],
                     "ttl":w["ttl"],"cum_at_copy":w["cum_at_copy"],"final_cum":final_cum,"win":win,"copy_ev":round(ev,3),
                     "leadf":w.get("leadf"),"live":PLACE,"pnl":round(pnl,2) if PLACE else None}
                open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
                if PLACE: s.realized+=pnl
                s.stats["settled"]+=1; w["settled"]=True; s.done.add(k); s.copied.pop(k,None)
                extra=f" pnl=${pnl:+.2f} cumReal=${s.realized:+.2f}" if PLACE else ""
                log(f"SETTLED {w['slug']} {w['side']} @{w['our_ask']} final=${final_cum} win={win}{extra}")
        for _ in range(3):
            if not _run: break
            await asyncio.sleep(1)
async def reporter(s):
    await asyncio.sleep(20)
    while _run:
        rows=[]
        try:
            for ln in open(OUTF,encoding="utf-8"):
                try: rows.append(json.loads(ln))
                except: pass
        except FileNotFoundError: pass
        if rows:
            def wr(rs): return sum(1 for r in rs if r["win"])/len(rs)*100 if rs else 0
            b13=[r for r in rows if 1000<=r["final_cum"]<3000]; b3=[r for r in rows if r["final_cum"]>=3000]
            tag=f" REAL pnl=${s.realized:+.2f} orders={s.orders_done}{' HALTED' if s.halted else ''}" if PLACE else ""
            log(f"STAT copied={s.stats['copied']} settled={len(rows)} | ALL WR={wr(rows):.0f}% | $1k-3k n={len(b13)} WR={wr(b13):.0f}% | $3k+ n={len(b3)} WR={wr(b3):.0f}%{tag}")
        for _ in range(30):
            if not _run: break
            await asyncio.sleep(1)
async def main():
    s=S(); cli=None
    if PLACE:
        cli=trader()
        try: bal=float(cli.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6; log(f"LIVE wallet ${bal:.2f}")
        except Exception as e: log(f"balance check failed: {str(e)[:60]}")
    await asyncio.gather(poller(s,cli),settler(s,cli),reporter(s))
if __name__=="__main__":
    log(f"copy_cum_probe START [{'LIVE --place, caps: %dsh/conc%d/total%d/stop$%g' %(SHARES,MAX_CONCURRENT,MAX_TOTAL_ORDERS,STOP_LOSS) if PLACE else 'DRY observe-only'}] copy fav when cum>=${COPY_MIN:.0f}")
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
