"""Paper LOAD-THE-WINNER engine backtest + anti-exhaustion filter comparison.
Loads the leading side when the underlying trends; compares filter modes to see if
'don't buy the exhausted/accelerating peak' + 'skip last minute' reduce reversal losses.
Fetches prices-history ONCE, simulates all modes. Fill model = 1-min prices-history (optimistic)."""
import json,re,httpx,time,math,sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
def p(*a): print(*a); sys.stdout.flush()
F="data/eebde_history_7d.jsonl"
SPREAD=0.02; STRONG=8.0
NEUTRAL_SIZE=0.0   # 0 = trend-only (the viable edge); neutral MM loses for us
LEAD_SIZE=1.0
NW=int(sys.argv[1]) if len(sys.argv)>1 else 600
def load_ok(al,prev_al,strong,mm,mN,MODE):
    last=(mm>=mN-1); accel=al>prev_al+1.0; persist=strong and prev_al>=STRONG
    if MODE==0: return strong
    if MODE==1: return persist
    if MODE==2: return strong and not last
    if MODE==3: return strong and not accel
    if MODE==4: return persist and (not last) and (not accel)
    return strong
mk={}
for ln in open(F,encoding="utf-8").read().split("\n"):
    ln=ln.strip()
    if not ln: continue
    try: r=json.loads(ln)
    except: continue
    if r.get("type")!="TRADE": continue
    m=re.match(r"(\w+)-updown-(5m|15m)-(\d+)",r.get("slug","") or "")
    if not m or r.get("outcome") not in ("Up","Down") or m.group(1) not in ("btc","eth"): continue
    cid=r["conditionId"]
    d=mk.setdefault(cid,{"coin":m.group(1),"dur":300 if m.group(2)=="5m" else 900,"start":int(m.group(3)),"Up":None,"Down":None})
    d[r["outcome"]]=r.get("asset")
mk={k:v for k,v in mk.items() if v["Up"] and v["Down"]}
cids=list(mk)[:NW]
p(f"windows: {len(cids)}")
ts=[mk[c]["start"] for c in cids]
def bn(sym,t0,t1):
    out={}; cur=t0*1000
    while cur<t1*1000:
        rr=httpx.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":int(cur),"endTime":int(t1*1000),"limit":1000},timeout=20).json()
        if not isinstance(rr,list) or not rr: break
        for k in rr: out[int(k[0]//1000)]=(float(k[1]),float(k[4]))
        cur=rr[-1][0]+60000
        if len(rr)<1000: break
    return out
p("binance...")
BN={"btc":bn("BTCUSDT",min(ts)-120,max(ts)+1000),"eth":bn("ETHUSDT",min(ts)-120,max(ts)+1000)}
def bpx(coin,t):
    d=BN[coin]
    for dd in range(4):
        if t+dd in d: return d[t+dd]
    return None
def hist(tok,s,e):
    try:
        rr=httpx.get("https://clob.polymarket.com/prices-history",params={"market":tok,"startTs":s,"endTs":e,"fidelity":"1"},timeout=10).json()
        return {int(x["t"]//60):x["p"] for x in (rr.get("history",[]) if isinstance(rr,dict) else [])}
    except: return {}
def fetch(cid):
    d=mk[cid]; st=d["start"]; settle=st+d["dur"]
    return cid,hist(d["Up"],st-60,settle+120),hist(d["Down"],st-60,settle+120)
p("prices-history (parallel)...")
H={}
with ThreadPoolExecutor(max_workers=20) as ex:
    for i,(cid,hu,hd) in enumerate(ex.map(fetch,cids)):
        H[cid]=(hu,hd)
        if i%150==0: p(f"  {i}/{len(cids)}")
def simulate(MODE,CAP=999):
    tot_pnl=tot_cost=0.0; nwin=wins=netlong=0; losses=[]
    for cid in cids:
        d=mk[cid]; coin=d["coin"]; st=d["start"]; settle=st+d["dur"]
        hu,hd=H[cid]
        if len(hu)<3 or len(hd)<3: continue
        up_win=hu[max(hu)]>=0.5
        o=bpx(coin,st)
        if not o: continue
        op=o[0]; m0=st//60; mN=settle//60
        upS=upC=dnS=dnC=0.0; pu=hu.get(m0); pd=hd.get(m0); prev_al=0.0
        for mm in range(m0+1,mN):
            c=bpx(coin,mm*60)
            lead=math.log(c[1]/op)*1e4 if c else 0.0
            fav="Up" if lead>=0 else "Down"; al=abs(lead); strong=al>=STRONG
            ok=load_ok(al,prev_al,strong,mm,mN,MODE)
            cu=hu.get(mm); cd=hd.get(mm)
            if cu is not None and pu is not None:
                if strong and fav=="Up":
                    if ok and upS<CAP:
                        bid=round(cu,2)
                        if 0.03<bid<0.97: upS+=LEAD_SIZE; upC+=LEAD_SIZE*bid
                elif strong and fav=="Down": pass
                else:
                    bid=round(pu-SPREAD,2)
                    if NEUTRAL_SIZE>0 and 0.03<bid<0.97 and cu<=bid: upS+=NEUTRAL_SIZE; upC+=NEUTRAL_SIZE*bid
            if cd is not None and pd is not None:
                if strong and fav=="Down":
                    if ok and dnS<CAP:
                        bid=round(cd,2)
                        if 0.03<bid<0.97: dnS+=LEAD_SIZE; dnC+=LEAD_SIZE*bid
                elif strong and fav=="Up": pass
                else:
                    bid=round(pd-SPREAD,2)
                    if NEUTRAL_SIZE>0 and 0.03<bid<0.97 and cd<=bid: dnS+=NEUTRAL_SIZE; dnC+=NEUTRAL_SIZE*bid
            pu=cu if cu is not None else pu; pd=cd if cd is not None else pd; prev_al=al
        cost=upC+dnC
        if cost<=0: continue
        winner_sh=upS if up_win else dnS; pnl=winner_sh-cost
        nwin+=1; tot_pnl+=pnl; tot_cost+=cost; wins+=(pnl>0)
        if pnl<0: losses.append(pnl)
        if (upS>dnS)==up_win: netlong+=1
    losses.sort()
    return {"n":nwin,"margin":(tot_pnl/tot_cost*100 if tot_cost else 0),"pnl":tot_pnl,"cost":tot_cost,
            "win":wins/max(nwin,1)*100,"nl":netlong/max(nwin,1)*100,
            "nloss":len(losses),"ltot":sum(losses),"worst":(losses[0] if losses else 0),"lpct":len(losses)/max(nwin,1)*100}
p(f"\n=== PER-WINDOW SHARE CAP comparison (BASE entry, vary max shares/side/window) ===")
p(f"{'cap':<14}{'n':>5}{'margin':>9}{'win%':>6}{'loss%':>7}{'worst':>8}{'lossTot':>9}{'PnL':>8}{'turnover':>10}")
for CAP in (1,2,3,5,999):
    r=simulate(0,CAP)
    lab=f"cap={CAP}" if CAP<999 else "UNLIMITED"
    p(f"{lab:<14}{r['n']:>5}{r['margin']:>+8.2f}%{r['win']:>5.0f}%{r['lpct']:>6.0f}%{r['worst']:>8.2f}{r['ltot']:>9.1f}{r['pnl']:>+8.1f}{r['cost']:>10.0f}")
