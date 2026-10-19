"""stop_param_sweep.py — sweep signal-stop params (STOP_BPS x CONFIRM secs) on ce25 historical
windows, with PRECISE reversal detection (binance 1s) and REALISTIC exit price (PM prices-history).
Answers: is there ANY (threshold, confirm) that makes the signal-stop beat hold-to-settle?
Fill model: entry=PM price at entry minute; exit-on-stop=PM price at stop minute (captures the
directional drop, not the bid-ask spread). For RELATIVE param comparison + vs HOLD."""
import json,re,httpx,math,sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
def p(*a): print(*a); sys.stdout.flush()
F="data/ce25_history_7d.jsonl"
STRONG=8.0; LATE=180   # enter at start+180s (minute 3) on the leading side, |lead|>=STRONG
NPER=int(sys.argv[1]) if len(sys.argv)>1 else 160
BSYM={'btc':'BTCUSDT','eth':'ETHUSDT','sol':'SOLUSDT','xrp':'XRPUSDT'}
GRID_BPS=[6,10,15,20]; GRID_CONF=[10,20,30]
mk=defaultdict(dict)
for ln in open(F,encoding="utf-8"):
    ln=ln.strip()
    if not ln: continue
    try: r=json.loads(ln)
    except: continue
    if r.get("type")!="TRADE": continue
    m=re.match(r"(btc|eth|sol|xrp)-updown-5m-(\d+)",r.get("slug","") or "")
    if not m or r.get("outcome") not in ("Up","Down"): continue
    d=mk[m.group(1)].setdefault(int(m.group(2)),{"Up":None,"Down":None}); d[r["outcome"]]=r.get("asset")
for c in mk: mk[c]={k:v for k,v in mk[c].items() if v["Up"] and v["Down"]}
def bn1s(sym,st):
    settle=st+300
    out={}
    r=httpx.get('https://api.binance.com/api/v3/klines',params={'symbol':sym,'interval':'1s','startTime':(st-2)*1000,'endTime':(settle+2)*1000,'limit':400},timeout=20).json()
    for k in r:
        if isinstance(k,list): out[int(k[0]//1000)]=float(k[4])
    return out
def ph(tok,st):
    try:
        r=httpx.get('https://clob.polymarket.com/prices-history',params={'market':tok,'startTs':st-60,'endTs':st+360,'fidelity':'1'},timeout=12).json()
        return {int(x['t']//60):x['p'] for x in (r.get('history',[]) if isinstance(r,dict) else [])}
    except: return {}
def fetch(args):
    coin,st=args
    up=mk[coin][st]['Up']
    return coin,st,bn1s(BSYM[coin],st),ph(up,st)
jobs=[]
for c in ('btc','eth','sol','xrp'):
    for st in sorted(mk[c])[:NPER]: jobs.append((c,st))
p('windows: %d'%len(jobs))
DATA=[]
with ThreadPoolExecutor(max_workers=10) as ex:
    for i,(coin,st,b1,hu) in enumerate(ex.map(fetch,jobs)):
        DATA.append((coin,st,b1,hu))
        if i%150==0: p('  %d/%d'%(i,len(jobs)))
def sim(stop_bps,conf):
    tot_hold=tot_stop=cost_sum=0.0; nstop=nfalse=n=0
    for coin,st,b1,hu in DATA:
        settle=st+300; m0=st//60; mN=settle//60
        if len(hu)<3 or len(b1)<60: continue
        op=None
        for dd in range(3):
            if st+dd in b1: op=b1[st+dd]; break
        if not op: continue
        up_win=hu[max(hu)]>=0.5
        # lead at entry
        et=st+LATE; cprice=None
        for dd in range(3):
            if et+dd in b1: cprice=b1[et+dd]; break
        if not cprice: continue
        lead=math.log(cprice/op)*1e4
        if abs(lead)<STRONG: continue
        side_up=(lead>=0); our=1 if side_up else -1
        emin=et//60
        cost=hu.get(emin)
        if cost is None or not (0.03<cost<0.97): continue
        won=(side_up==up_win)
        hold_pnl=(1.0-cost) if won else (-cost)
        # walk 1s for reversal >= stop_bps against us, sustained >= conf
        rev_since=None; stop_pnl=None
        for t in range(et+1,settle):
            px=b1.get(t)
            if px is None: continue
            ld=math.log(px/op)*1e4
            if our*ld <= -stop_bps:
                if rev_since is None: rev_since=t
                elif t-rev_since>=conf:
                    exmin=t//60
                    expx=hu.get(exmin) or hu.get(exmin-1) or cost
                    stop_pnl=(expx-cost);
                    break
            else: rev_since=None
        if stop_pnl is None: stop_pnl=hold_pnl
        else:
            nstop+=1
            if won: nfalse+=1   # we stopped a trade that would have won
        n+=1; cost_sum+=cost; tot_hold+=hold_pnl; tot_stop+=stop_pnl
    return n,tot_hold,tot_stop,cost_sum,nstop,nfalse
n0,h0,_,c0,_,_=sim(999,999)  # no stop ever -> pure hold baseline
p('\nHOLD baseline: n=%d  margin=%+.1f%%'%(n0,h0/c0*100 if c0 else 0))
p('\n=== STOP PARAM SWEEP (margin%% ; vs hold) ===')
p('%-8s'%'bps\\conf'+''.join('%12s'%('conf=%ds'%cf) for cf in GRID_CONF))
for bps in GRID_BPS:
    row='%-8d'%bps
    for cf in GRID_CONF:
        n,h,s,cc,ns,nf=sim(bps,cf)
        m=s/cc*100 if cc else 0
        row+='%12s'%('%+.1f%%(%d/%d)'%(m,nf,ns))
    p(row)
p('\n(cell = stop-margin%% (falseStops/totalStops); compare to HOLD %+.1f%%)'%(h0/c0*100 if c0 else 0))
