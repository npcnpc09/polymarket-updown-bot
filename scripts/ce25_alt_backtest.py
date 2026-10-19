"""ce25_alt_backtest.py — per-COIN backtest of load-the-winner across btc/eth/sol/xrp.
Uses ce25's trade log (data/ce25_history_7d.jsonl) for the token IDs of ALT updown windows
(gamma de-indexes settled windows, so this whale log is the only historical alt token source).
Reports, per coin:
  (1) CERTAINTY = unconditional leading-side win% (fill-model-INDEPENDENT — the clean signal metric)
  (2) load-the-winner margin (fill model = 1-min prices-history price = OPTIMISTIC; see backtest-trap memory)
Aggregate-only (no raw persisted). Fetches prices-history once per window via ThreadPool(15)."""
import json,re,httpx,math,sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
def p(*a): print(*a); sys.stdout.flush()
F="data/ce25_history_7d.jsonl"
STRONG=8.0; LATE_FRAC=0.55; CAP=1; SPREAD=0.0
BSYM={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT","xrp":"XRPUSDT"}
CAP_PER_COIN=int(sys.argv[1]) if len(sys.argv)>1 else 900
mk=defaultdict(dict)  # coin -> {start: (up,dn)}
for ln in open(F,encoding="utf-8"):
    ln=ln.strip()
    if not ln: continue
    try: r=json.loads(ln)
    except: continue
    if r.get("type")!="TRADE": continue
    m=re.match(r"(btc|eth|sol|xrp)-updown-5m-(\d+)",r.get("slug","") or "")
    if not m or r.get("outcome") not in ("Up","Down"): continue
    coin=m.group(1); st=int(m.group(2)); d=mk[coin].setdefault(st,{"Up":None,"Down":None})
    d[r["outcome"]]=r.get("asset")
for coin in mk:
    mk[coin]={k:v for k,v in mk[coin].items() if v["Up"] and v["Down"]}
p("unique windows w/ both tokens:",{c:len(mk[c]) for c in mk})
def bn(sym,t0,t1):
    out={}; cur=t0*1000
    while cur<t1*1000:
        rr=httpx.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":int(cur),"endTime":int(t1*1000),"limit":1000},timeout=20).json()
        if not isinstance(rr,list) or not rr: break
        for k in rr: out[int(k[0]//1000)]=(float(k[1]),float(k[4]))
        cur=rr[-1][0]+60000
        if len(rr)<1000: break
    return out
def hist(tok,s,e):
    try:
        rr=httpx.get("https://clob.polymarket.com/prices-history",params={"market":tok,"startTs":s,"endTs":e,"fidelity":"1"},timeout=12).json()
        return {int(x["t"]//60):x["p"] for x in (rr.get("history",[]) if isinstance(rr,dict) else [])}
    except: return {}
RES={}
for coin in ("btc","eth","sol","xrp"):
    wins=sorted(mk[coin])[:CAP_PER_COIN]
    if not wins: continue
    p(f"\n[{coin}] {len(wins)} windows — binance {BSYM[coin]}...")
    BN=bn(BSYM[coin],min(wins)-120,max(wins)+400)
    def bpx(t):
        for dd in range(4):
            if t+dd in BN: return BN[t+dd]
        return None
    def fetch(st):
        up,dn=mk[coin][st]["Up"],mk[coin][st]["Down"]
        return st,hist(up,st-60,st+360)
    H={}
    p(f"[{coin}] prices-history (parallel)...")
    with ThreadPoolExecutor(max_workers=15) as ex:
        for i,(st,hu) in enumerate(ex.map(fetch,wins)):
            H[st]=hu
            if i and i%200==0: p(f"   {i}/{len(wins)}")
    # simulate
    n=cert_n=cert_win=0; tot_pnl=tot_cost=0.0; nl=wins_n=0; losses=[]
    for st in wins:
        settle=st+300; hu=H.get(st,{})
        if len(hu)<3: continue
        up_win=hu[max(hu)]>=0.5
        o=bpx(st)
        if not o: continue
        op=o[0]; m0=st//60; mN=settle//60
        # CERTAINTY: leading side at the realistic ENTRY point (~LATE_FRAC into the window,
        # = 2 min before settle), NOT 1-min-before (that's a look-ahead artifact). Unconditional.
        entry_min=m0+3  # 3min into a 5min window = settle-2min ~= LATE_FRAC entry
        clate=bpx(entry_min*60)
        if clate:
            lead_late=math.log(clate[1]/op)*1e4
            if abs(lead_late)>=STRONG:
                cert_n+=1; lead_side="Up" if lead_late>=0 else "Down"
                cert_win+=int((lead_side=="Up")==up_win)
        # load-the-winner margin (optimistic fill at prices-history)
        upS=upC=dnS=dnC=0.0
        for mm in range(m0+1,mN):
            if (mm*60-st)/300<LATE_FRAC: continue
            c=bpx(mm*60)
            if not c: continue
            lead=math.log(c[1]/op)*1e4; al=abs(lead)
            if al<STRONG: continue
            fav="Up" if lead>=0 else "Down"
            pxh=hu.get(mm)
            if pxh is None or not(0.03<pxh<0.97): continue
            if fav=="Up" and upS<CAP: upS+=1; upC+=pxh
            elif fav=="Down" and dnS<CAP: dnS+=1; dnC+=pxh
        cost=upC+dnC
        if cost<=0: continue
        winner_sh=upS if up_win else dnS; pnl=winner_sh-cost
        n+=1; tot_pnl+=pnl; tot_cost+=cost; wins_n+=(pnl>0)
        if pnl<0: losses.append(pnl)
        if (upS>dnS)==up_win: nl+=1
    losses.sort()
    RES[coin]={"n":n,"cert_n":cert_n,"cert":cert_win/max(cert_n,1)*100,
               "margin":tot_pnl/tot_cost*100 if tot_cost else 0,"pnl":tot_pnl,"cost":tot_cost,
               "win":wins_n/max(n,1)*100,"nl":nl/max(n,1)*100,
               "lpct":len(losses)/max(n,1)*100,"worst":(losses[0] if losses else 0)}
p("\n"+"="*78)
p(f"{'coin':<6}{'n':>5}{'CERTAINTY':>11}{'lwMargin':>10}{'win%':>6}{'netLongW%':>11}{'loss%':>7}{'worst':>8}")
p(f"{'':6}{'':5}{'(lead-side win%)':>11}")
for c in ("btc","eth","sol","xrp"):
    r=RES.get(c)
    if not r: continue
    p(f"{c:<6}{r['n']:>5}{r['cert']:>9.0f}% {r['margin']:>+8.1f}%{r['win']:>5.0f}%{r['nl']:>10.0f}%{r['lpct']:>6.0f}%{r['worst']:>8.2f}")
p("="*78)
p("CERTAINTY = unconditional leading-side win% (clean signal metric, fill-model-independent).")
p("lwMargin = load-the-winner margin with OPTIMISTIC prices-history fill (overstated; for RELATIVE coin compare only).")
