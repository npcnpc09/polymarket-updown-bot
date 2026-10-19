"""Backtest OUR directional taker on 5m vs 15m. ce25 token-ids; underlying lead/max_lead from
binance; entry = leading side at LATE point (0.6*dur); entry PRICE + resolution from Up-token
prices-history. Same (optimistic) fill model both durations -> RELATIVE 5m-vs-15m comparison valid."""
import json,re,httpx,math,sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
NPER=int(sys.argv[1]) if len(sys.argv)>1 else 120
BSYM={'btc':'BTCUSDT','eth':'ETHUSDT'}
mk=defaultdict(dict)  # (coin,dur) -> {start: up_token}
for ln in open('data/ce25_history_7d.jsonl',encoding='utf-8'):
    ln=ln.strip()
    if not ln: continue
    try: r=json.loads(ln)
    except: continue
    if r.get('type')!='TRADE': continue
    m=re.match(r'(btc|eth)-updown-(5m|15m)-(\d+)',r.get('slug','') or '')
    if m and r.get('outcome')=='Up':
        du=300 if m.group(2)=='5m' else 900
        mk[(m.group(1),du)][int(m.group(3))]=r.get('asset')
def bn(sym,t0,t1):
    out={}
    r=httpx.get('https://api.binance.com/api/v3/klines',params={'symbol':sym,'interval':'1m','startTime':t0*1000,'endTime':t1*1000,'limit':500},timeout=15).json()
    for k in r:
        if isinstance(k,list): out[int(k[0]//1000)]=(float(k[1]),float(k[2]),float(k[3]),float(k[4]))
    return out
def uph(tok,st,du):
    try:
        r=httpx.get('https://clob.polymarket.com/prices-history',params={'market':tok,'startTs':st-60,'endTs':st+du+120,'fidelity':'1'},timeout=12).json()
        return {int(x['t']//60):x['p'] for x in (r.get('history',[]) if isinstance(r,dict) else [])}
    except: return {}
def job(args):
    coin,du,st=args; settle=st+du; m0=st//60
    bnd=bn(BSYM[coin],st-120,settle+60); h=uph(mk[(coin,du)][st],st,du)
    if len(h)<3: return None
    o=bnd.get(st) or bnd.get(st+1)
    if not o: return None
    op=o[0]; ent=st+int(0.6*du)  # late entry ~0.6 of window
    peak=0.0
    for mm in range(0,int(0.6*du)//60+1):
        c=bnd.get(st+mm*60)
        if c: peak=max(peak,abs(math.log(c[2]/op)*1e4),abs(math.log(c[1]/op)*1e4))
    ce=bnd.get(ent)
    if not ce: return None
    lead=math.log(ce[3]/op)*1e4
    up_win=h[max(h)]>=0.5
    up_pe=h.get(ent//60) or h.get(ent//60-1)
    if up_pe is None: return None
    side_up=lead>=0; B=up_pe if side_up else (1-up_pe)
    won=(side_up==up_win)
    return du,peak,abs(lead),B,won
jobs=[]
for (coin,du) in mk:
    for st in sorted(mk[(coin,du)])[-NPER:]: jobs.append((coin,du,st))
print('testing %d windows...'%len(jobs))
data=[]
with ThreadPoolExecutor(max_workers=12) as ex:
    for i,r in enumerate(ex.map(job,jobs)):
        if r: data.append(r)
        if i%150==0: print('  %d/%d'%(i,len(jobs)))
def stat(rows,lab):
    rows=[r for r in rows if r[1]>=15]  # max_lead>=15
    if not rows: print('  %s (none)'%lab); return
    n=len(rows); w=sum(1 for r in rows if r[4]); pnl=sum((1-r[3])*5 if r[4] else -r[3]*5 for r in rows)
    cost=sum(r[3]*5 for r in rows); avgB=sum(r[3] for r in rows)/n
    print('  %-6s n=%-4d win%%=%.0f%%  avgEntry=%.2f  avgEV=%+.3f  margin=%+.1f%%'%(lab,n,w/n*100,avgB,pnl/n,pnl/cost*100 if cost else 0))
print('\n=== OUR taker, max_lead>=15, 5m vs 15m (optimistic fill, RELATIVE compare) ===')
stat([r for r in data if r[0]==300],'5m')
stat([r for r in data if r[0]==900],'15m')
print('\n(15m favorite wins more (91%) BUT priced higher -> does avgEV actually beat 5m for a taker?)')
