"""
strategy_paper_6e1d.py
Reconstructed 0x6e1d strategy as a pure model, with two modes:

  --validate   Offline: replay his real trades, independently recompute MY
               signal at his trade time, report agreement per market-type.
  --live       Forward paper: poll live BTC spot + active BTC markets + his
               activity; place paper orders from MY strategy; log his real
               trades; report rolling agreement. Lightweight single process.

Strategy (see memory/strategy_6e1d_btc_model_edge.md):
  price each BTC threshold market with driftless lognormal
  p_above = Phi(ln(S/K)/(sigma*sqrt(tau))), sigma ~16% annualized;
  BUY the side where p_model - ask > MARGIN.
"""
import httpx, json, math, time, os, re, argparse, datetime as dt
from collections import defaultdict

ADDR     = "0x6e1d5040d0ac73709b0621f620d2a60b80d2d0fa"
SIGMA_ANN= 0.16
MIN_PER_YR = 525600.0
SIGMA_MIN= SIGMA_ANN/math.sqrt(MIN_PER_YR)
MARGIN   = 0.04
PAPER_SZ = 20.0
CACHE    = "data/6e1d_mkt_cache.json"
LOG      = "data/strategy_paper_6e1d.jsonl"
sess = httpx.Client(timeout=25, headers={"User-Agent":"Mozilla/5.0"})

def Phi(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
def parse_iso(s):
    try: return dt.datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()
    except: return None

# ---------- market parsing + model ----------
def parse_market(q):
    """-> (mtype, strikes[list]) or (None,None). Crypto threshold markets."""
    s=q.lower().replace(",","")
    nums=[]
    for m in re.finditer(r"\$?\s*(\d+(?:\.\d+)?)\s*(k)?", s):
        v=float(m.group(1))*(1000 if m.group(2) else 1)
        if 1000<=v<=1000000: nums.append(v)
    if "between" in s and len(nums)>=2: return ("range", sorted(nums[:2]))
    if "up or down" in s:               return ("updown", [])
    if ("reach" in s or "hit" in s) and nums: return ("touch_above", [nums[0]])
    if "dip" in s and nums:             return ("touch_below", [nums[0]])
    if ("above" in s or "at least" in s or "more than" in s or "exceed" in s) and nums:
        return ("above", [nums[0]])
    if ("below" in s or "under" in s or "less than" in s) and nums:
        return ("below", [nums[0]])
    return (None,None)

def model_p_yes(mtype, strikes, S, tau_min, open_px=None):
    """P('Yes' outcome) under driftless lognormal."""
    if tau_min<=0 or S<=0: return None
    v=SIGMA_MIN*math.sqrt(tau_min)
    def p_above(K): return Phi(math.log(S/K)/v)
    if mtype=="above":        return p_above(strikes[0])
    if mtype=="below":        return 1-p_above(strikes[0])
    if mtype=="range":        return p_above(strikes[0])-p_above(strikes[1])
    if mtype=="touch_above":
        K=strikes[0]
        return 1.0 if S>=K else min(1.0, 2*(1-Phi(math.log(K/S)/v)))
    if mtype=="touch_below":
        K=strikes[0]
        return 1.0 if S<=K else min(1.0, 2*Phi(math.log(K/S)/(-v) if False else -math.log(S/K)/v))
    if mtype=="updown":
        ref=open_px if open_px else S
        return p_above(ref)
    return None

def signal(mtype, strikes, S, tau_min, ask_yes, ask_no, open_px=None):
    """Return ('Yes'/'No', fair, edge) for the side MY strategy would buy, else None."""
    p=model_p_yes(mtype,strikes,S,tau_min,open_px)
    if p is None: return None
    best=None
    if ask_yes is not None and p-ask_yes>MARGIN:        best=("Yes",p,p-ask_yes)
    if ask_no  is not None and (1-p)-ask_no>MARGIN:
        e=(1-p)-ask_no
        if best is None or e>best[2]: best=("No",1-p,e)
    return best

# ---------- shared data ----------
def load_cache(): return json.load(open(CACHE)) if os.path.exists(CACHE) else {}
def save_cache(c): json.dump(c, open(CACHE,"w"))

def backfill_buys(max_pages, crypto_only=True):
    buys=[]; before=None; pages=0; newest=None
    while pages<max_pages:
        p={"user":ADDR,"limit":500}
        if before:p["end"]=before
        pg=sess.get("https://data-api.polymarket.com/activity",params=p).json()
        if not pg:break
        pages+=1
        if newest is None:newest=max(a["timestamp"] for a in pg)
        for a in pg:
            if a.get("type")=="TRADE" and a.get("side")=="BUY":
                buys.append(a)
        o=min(a["timestamp"] for a in pg)
        if before is not None and o>=before:break
        before=o-1
        if len(pg)<500:break
    return buys,newest

def fetch_meta(cids, cache):
    need=[c for c in cids if c not in cache]
    for i in range(0,len(need),20):
        batch=need[i:i+20]
        try:
            d=sess.get("https://gamma-api.polymarket.com/markets",
               params=[("closed","true")]+[("condition_ids",c) for c in batch]).json()
        except Exception: d=[]
        for m in (d if isinstance(d,list) else []):
            op=None
            try: op=[float(x) for x in json.loads(m.get("outcomePrices","[]"))]
            except: pass
            cache[m.get("conditionId")]=dict(q=m.get("question",""),
                end=m.get("endDate"),op=op)
    return cache

def binance_px(t0,t1):
    px={}; cur=(t0-120)*1000; end=(t1+120)*1000
    while cur<end:
        kl=sess.get("https://api.binance.com/api/v3/klines",
            params={"symbol":"BTCUSDT","interval":"1m","startTime":int(cur),
                    "endTime":int(end),"limit":1000}).json()
        if not kl:break
        for k in kl: px[int(k[0]//60000)]=float(k[4])
        cur=kl[-1][0]+60000
        if len(kl)<1000:break
    return px

# ---------- VALIDATE ----------
def run_validate(days=14):
    print(f"=== VALIDATE: replay 6e1d trades, compare to MY signal "
          f"(sigma={SIGMA_ANN:.0%}, margin={MARGIN}) ===")
    buys,newest=backfill_buys(max_pages=70)
    cut=newest-days*86400
    buys=[b for b in buys if b["timestamp"]>=cut]
    cache=load_cache(); fetch_meta({b["conditionId"] for b in buys},cache); save_cache(cache)
    t0=min(b["timestamp"] for b in buys); t1=max(b["timestamp"] for b in buys)
    print(f"  {len(buys)} BUYs / {days}d; fetching BTC spot...")
    px=binance_px(t0,t1)
    def spot(ts):
        mi=int(ts//60)
        for d in range(6):
            if mi-d in px: return px[mi-d]
        return None

    per=defaultdict(lambda:[0,0,0,0])  # type->[his_trades, priced, my_signal_fired, agree_same_side]
    edge_hit=[0,0]  # [his trades my model also flags as +edge his-side, total priced]
    # realized EV split: mirror his side at his price, $1 flat, hold-to-redeem
    split={"flagged":[0,0,0.0], "not":[0,0,0.0]}   # key->[n, wins, pnl$]
    for b in buys:
        mtype,strikes=parse_market(b.get("title",""))
        per[mtype or "unparsed"][0]+=1
        if mtype is None or mtype=="updown": continue
        m=cache.get(b["conditionId"]);
        if not m or not m.get("end"): continue
        S=spot(b["timestamp"]);
        if not S: continue
        tau=(parse_iso(m["end"])-b["timestamp"])/60.0
        if tau<=1: continue
        per[mtype][1]+=1
        p=model_p_yes(mtype,strikes,S,tau)
        if p is None: continue
        his_side=b.get("outcome","")
        p_his= p if his_side.lower()=="yes" else 1-p
        flagged = (p_his - b.get("price",0) > MARGIN)
        if flagged:
            edge_hit[0]+=1; per[mtype][3]+=1
        edge_hit[1]+=1
        # realized PnL of mirroring this exact trade ($1 flat)
        op=m.get("op"); oidx=b.get("outcomeIndex"); price=b.get("price",0)
        if op and len(op)>oidx and price>0 and max(op)>0.99:
            win = op[oidx]>0.99
            pnl = (1.0/price - 1.0) if win else -1.0
            k="flagged" if flagged else "not"
            split[k][0]+=1; split[k][1]+=(1 if win else 0); split[k][2]+=pnl
    print(f"\n{'type':>14} {'his_n':>7} {'priced':>7} {'my_model_agrees':>16}")
    for t,(hn,pr,fired,agree) in sorted(per.items(),key=lambda x:-x[1][0]):
        ag=f"{agree/pr*100:.0f}% ({agree}/{pr})" if pr else "-"
        print(f"{t:>14} {hn:>7} {pr:>7} {ag:>16}")
    if edge_hit[1]:
        print(f"\nOVERALL: of {edge_hit[1]} priced trades, MY model independently flags "
              f"his chosen side as +edge (>{MARGIN}) in {edge_hit[0]} = "
              f"{edge_hit[0]/edge_hit[1]*100:.0f}%")
    print("\n=== DECISIVE: realized PnL of his trades, split by whether MY model flagged them ===")
    print(f"  (mirror his side at his price, $1 flat, hold-to-redeem)")
    for k in ("flagged","not"):
        n,w,pnl=split[k]
        if n: print(f"  {k:>8}: n={n:6d}  WR={w/n*100:5.1f}%  PnL=${pnl:+8.2f}  "
                    f"EV/trade={pnl/n*100:+5.1f}%")
    print("  => if 'flagged' EV >> 'not' EV, MY strategy correctly isolates his alpha subset.")

# ---------- LIVE ----------
def fetch_open_market(cid, omcache):
    """Fetch OPEN market meta by conditionId (no closed filter). Cache in dict."""
    if cid in omcache: return omcache[cid]
    info=None
    try:
        d=sess.get("https://gamma-api.polymarket.com/markets",
                   params={"condition_ids":cid}).json()
        m=d[0] if isinstance(d,list) and d else None
        if m:
            mtype,strikes=parse_market(m.get("question",""))
            try: toks=json.loads(m.get("clobTokenIds","[]"))
            except: toks=[]
            try: outs=json.loads(m.get("outcomes","[]"))
            except: outs=[]
            end=parse_iso(m.get("endDate"))
            if mtype and len(toks)>=2 and end:
                info=dict(cid=cid,q=m.get("question",""),mtype=mtype,
                          strikes=strikes,end=end,toks=toks,
                          outs=(outs if len(outs)>=2 else ["Yes","No"]),
                          closed=m.get("closed"))
    except Exception: pass
    omcache[cid]=info
    return info

def clob_ask(token):
    try:
        d=sess.get("https://clob.polymarket.com/price",
                   params={"token_id":token,"side":"buy"}).json()
        return float(d.get("price",0)) or None
    except Exception: return None

def live_spot():
    try:
        d=sess.get("https://api.binance.com/api/v3/ticker/price",
                   params={"symbol":"BTCUSDT"}).json()
        return float(d["price"])
    except Exception: return None

_open_cache={}
def updown_open(endts):
    """BTC open price at endDate-24h (period open for 'Up or Down on <date>')."""
    k=int(endts-86400)
    if k in _open_cache: return _open_cache[k]
    o=None
    try:
        kl=sess.get("https://api.binance.com/api/v3/klines",
            params={"symbol":"BTCUSDT","interval":"1m","startTime":int(k*1000),
                    "endTime":int((k+120)*1000),"limit":2}).json()
        if kl: o=float(kl[0][1])
    except Exception: pass
    _open_cache[k]=o; return o

def logline(obj):
    obj["t"]=int(time.time())
    open(LOG,"a").write(json.dumps(obj)+"\n")

def run_live(interval=60):
    print(f"=== LIVE paper (sigma={SIGMA_ANN:.0%} margin={MARGIN} size=${PAPER_SZ}) "
          f"poll={interval}s  log={LOG} ===  Ctrl-C to stop")
    omcache={}          # cid -> open-market meta
    my_open={}          # (cid,side) -> my paper order
    his_seen=set()      # txhash
    universe={}         # cid -> last_seen_ts (markets he's active in, last ~3h)
    agree=disagree=mine=0
    while True:
        loop_t=int(time.time())
        S=live_spot()
        # ---- pull his recent BTC trades ----
        try:
            acts=sess.get("https://data-api.polymarket.com/activity",
                          params={"user":ADDR,"limit":200}).json()
        except Exception: acts=[]
        new_his=[]
        for a in acts:
            if a.get("type")!="TRADE" or a.get("side")!="BUY": continue
            q=(a.get("title","") or "")
            if not any(k in q.lower() for k in ("bitcoin","btc")): continue
            universe[a["conditionId"]]=loop_t
            h=a.get("transactionHash")
            if h in his_seen: continue
            his_seen.add(h); new_his.append(a)
        # ---- per-his-trade: does MY model agree? (direct verdict) ----
        for a in sorted(new_his,key=lambda x:x["timestamp"]):
            if not S: break
            mtype,strikes=parse_market(a.get("title",""))
            m=fetch_open_market(a["conditionId"],omcache)
            verdict="?"; my_edge=None; fair=None
            if m and mtype and m.get("end"):
                tau=(m["end"]-a["timestamp"])/60.0
                opx=updown_open(m["end"]) if mtype=="updown" else None
                p=model_p_yes(mtype,strikes,S,tau,opx)
                if p is not None and tau>1:
                    side=a.get("outcome","")
                    p_his=p if side.lower() in ("yes","up") else 1-p
                    fair=round(p_his,3); my_edge=round(p_his-a.get("price",0),3)
                    verdict="AGREE" if my_edge>MARGIN else "skip"
            if verdict=="AGREE": agree+=1
            elif verdict=="skip": disagree+=1
            logline(dict(ev="HIS_TRADE",cid=a["conditionId"],q=a.get("title",""),
                side=a.get("outcome"),price=a.get("price"),usd=a.get("usdcSize"),
                my_fair=fair,my_edge=my_edge,verdict=verdict))
            print(f"  [HIS ] {a.get('outcome'):4} {a.get('title','')[:46]:46} "
                  f"px={a.get('price'):<6.3} fair={fair} edge={my_edge} -> {verdict}")
        # ---- MY independent paper orders on the live universe ----
        cutoff=loop_t-3*3600
        for cid in [c for c,t in universe.items() if t>=cutoff]:
            m=fetch_open_market(cid,omcache)
            if not m or not S: continue
            tau=(m["end"]-loop_t)/60.0
            if tau<=2: continue
            ask_y=clob_ask(m["toks"][0]); ask_n=clob_ask(m["toks"][1])
            opx=updown_open(m["end"]) if m["mtype"]=="updown" else None
            sig=signal(m["mtype"],m["strikes"],S,tau,ask_y,ask_n,opx)
            if not sig: continue
            side,fair,edge=sig
            actual=m["outs"][0] if side=="Yes" else m["outs"][1]   # Up/Down or Yes/No
            key=(cid,actual)
            if key in my_open: continue
            ask=ask_y if side=="Yes" else ask_n
            my_open[key]=dict(q=m["q"],side=actual,fair=round(fair,3),ask=ask,
                edge=round(edge,3),spot=S,ts=loop_t)
            mine+=1
            logline(dict(ev="MY_ORDER",cid=cid,q=m["q"],side=actual,fair=round(fair,3),
                ask=ask,edge=round(edge,3),spot=S,size=PAPER_SZ))
            print(f"  [MINE] {actual:4} {m['q'][:46]:46} ask={ask} fair={fair:.2f} edge=+{edge:.2f}")
        tot=agree+disagree
        print(f"  -- spot={S} universe={sum(1 for t in universe.values() if t>=cutoff)} "
              f"| his_new={len(new_his)} agree={agree} skip={disagree} "
              f"agree_rate={agree/tot*100 if tot else 0:.0f}% my_orders={mine} -- "
              f"{dt.datetime.now().strftime('%H:%M:%S')}")
        time.sleep(interval)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--validate",action="store_true")
    ap.add_argument("--live",action="store_true")
    ap.add_argument("--days",type=int,default=14)
    ap.add_argument("--interval",type=int,default=60)
    ap.add_argument("--margin",type=float,default=MARGIN)
    ap.add_argument("--sigma",type=float,default=SIGMA_ANN)
    a=ap.parse_args()
    MARGIN=a.margin; SIGMA_ANN=a.sigma; SIGMA_MIN=SIGMA_ANN/math.sqrt(MIN_PER_YR)
    if a.validate: run_validate(a.days)
    elif a.live:   run_live(a.interval)
    else: print("use --validate or --live")
