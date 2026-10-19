"""Multi-day OOS test of 'skip when PM strongly disagrees (B<0.40)'. Uses ce25 token-ids;
entry=min3; B = our-side PM price at min3 (from Up-token prices-history; Down=1-up); resolution=
prices-history last; lead/max_lead from binance. Groups by DAY -> does skip-B<0.40 help EVERY day?"""
import json,re,httpx,math,datetime,sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
NPER=int(sys.argv[1]) if len(sys.argv)>1 else 120
BSYM={'btc':'BTCUSDT','eth':'ETHUSDT'}
mk=defaultdict(dict)
for ln in open('data/ce25_history_7d.jsonl',encoding='utf-8'):
    ln=ln.strip()
    if not ln: continue
    try: r=json.loads(ln)
    except: continue
    if r.get('type')!='TRADE': continue
    m=re.match(r'(btc|eth)-updown-5m-(\d+)',r.get('slug','') or '')
    if m and r.get('outcome')=='Up': mk[m.group(1)][int(m.group(2))]=r.get('asset')
def bn(sym,t0,t1):
    out={}; r=httpx.get('https://api.binance.com/api/v3/klines',params={'symbol':sym,'interval':'1m','startTime':t0*1000,'endTime':t1*1000,'limit':500},timeout=15).json()
    for k in r:
        if isinstance(k,list): out[int(k[0]//1000)]=(float(k[1]),float(k[3]),float(k[2]),float(k[4]))
    return out
def uph(tok,st):
    try:
        r=httpx.get('https://clob.polymarket.com/prices-history',params={'market':tok,'startTs':st-60,'endTs':st+360,'fidelity':'1'},timeout=12).json()
        return {int(x['t']//60):x['p'] for x in (r.get('history',[]) if isinstance(r,dict) else [])}
    except: return {}
def job(args):
    coin,st=args; settle=st+300; m0=st//60
    bnd=bn(BSYM[coin],st-120,settle+60); h=uph(mk[coin][st],st)
    if len(h)<3: return None
    o=bnd.get(st) or bnd.get(st+1)
    if not o: return None
    op=o[0]
    # max_lead over window (using highs/lows) and lead at min3
    peak=0.0
    for mm in range(5):
        c=bnd.get(st+mm*60)
        if c: peak=max(peak,abs(math.log(c[2]/op)*1e4),abs(math.log(c[1]/op)*1e4))
    c3=bnd.get(st+180)
    if not c3: return None
    lead3=math.log(c3[3]/op)*1e4
    up_win=h[max(h)]>=0.5
    up_p3=h.get(m0+3) or h.get(m0+2)
    if up_p3 is None: return None
    side_up=lead3>=0
    B=up_p3 if side_up else (1-up_p3)
    won=(side_up==up_win)
    return coin,st,peak,B,won
jobs=[]
for c in ('btc','eth'):
    for st in sorted(mk[c])[-NPER:]: jobs.append((c,st))
print('testing %d windows...'%len(jobs))
data=[]
with ThreadPoolExecutor(max_workers=12) as ex:
    for i,r in enumerate(ex.map(job,jobs)):
        if r: data.append(r)
        if i%120==0: print('  %d/%d'%(i,len(jobs)))
rows=[{'ml':peak,'B':B,'won':won,'pnl':(1-B)*5 if won else -B*5,
       'day':datetime.datetime.utcfromtimestamp(st).strftime('%m-%d')} for coin,st,peak,B,won in data if peak>=15]
days=sorted(set(r['day'] for r in rows))
print('\nbtc/eth max_lead>=15: %d trades across %d days %s\n'%(len(rows),len(days),days))
def ev(sub):
    if not sub: return 0,0,0
    n=len(sub); w=sum(1 for r in sub if r['won']); pnl=sum(r['pnl'] for r in sub)
    return n,w/n*100,pnl/n
print('%-22s%7s%7s%9s'%('filter','n','win%','avgEV')+'  per-day avgEV (want + every day)')
for nm,f in (('BASELINE all',lambda r:True),('skip B<0.40',lambda r:r['B']>=0.40),('skip B<0.50',lambda r:r['B']>=0.50)):
    sub=[r for r in rows if f(r)]; n,wr,avg=ev(sub)
    pd={d:round(ev([r for r in sub if r['day']==d])[2],2) for d in days}
    print('%-22s%7d%6.0f%%%+9.3f  %s'%(nm,n,wr,avg,pd))
# the cut bucket per day
print('\nB<0.40 bucket (the cut) per-day avgEV:')
for d in days:
    sub=[r for r in rows if r['B']<0.40 and r['day']==d]
    if sub: print('  %s: n=%d avgEV=%+.2f'%(d,len(sub),ev(sub)[2]))
