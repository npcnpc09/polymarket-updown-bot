"""OOS backtest of the |1h| 15-40 skip-gate. For every btc/eth 5m window in the 7-day ce25 history:
replicate the live entry (peak |lead| over min0-3 >= 15, take the leading side), compute 1h |trend|
magnitude at entry, resolve via binance net (=Chainlink at >=5bps). Report win% BY DAY BY band so we
can see if |1h| 15-40 is reliably the worst (gate robust) or regime noise (gate overfit)."""
import json,re,httpx,math,datetime,sys
from collections import defaultdict
starts=defaultdict(set)
for ln in open('data/ce25_history_7d.jsonl',encoding='utf-8'):
    ln=ln.strip()
    if not ln: continue
    try: r=json.loads(ln)
    except: continue
    m=re.match(r'(btc|eth)-updown-5m-(\d+)',r.get('slug','') or '')
    if m: starts[m.group(1)].add(int(m.group(2)))
SYM={'btc':'BTCUSDT','eth':'ETHUSDT'}
def bn(sym,t0,t1):
    out={};cur=t0
    while cur<t1:
        k=httpx.get('https://api.binance.com/api/v3/klines',params={'symbol':sym,'interval':'1m','startTime':cur*1000,'endTime':t1*1000,'limit':1000},timeout=20).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=float(x[4])
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
def band(n):
    a=abs(n)
    return '0-15' if a<15 else ('15-40' if a<40 else '40+')
rows=[]
for c in SYM:
    ws=sorted(starts[c])
    if not ws: continue
    d=bn(SYM[c],min(ws)-3700,max(ws)+360)
    def px(t):
        for dd in range(4):
            if t+dd in d: return d[t+dd]
        return None
    for st in ws:
        op=px(st); pe=px(st+180); cl=px(st+240) or px(st+300); p1=px(st+180-3600)
        if not(op and pe and cl and p1): continue
        # peak |lead| over min0..3 (replicate engine entry on max_lead>=15)
        peak=0
        for mm in range(4):
            q=px(st+mm*60)
            if q: peak=max(peak,abs(math.log(q/op)*1e4))
        if peak<15: continue
        lead=math.log(pe/op)*1e4
        if abs(lead)<3: continue
        side='Up' if lead>=0 else 'Down'
        n1h=math.log(pe/p1)*1e4
        won=(side=='Up')==(cl>=op)
        rows.append({'day':datetime.datetime.utcfromtimestamp(st).strftime('%m-%d'),'band':band(n1h),'won':won})
days=sorted(set(r['day'] for r in rows))
def wr(rs): return (sum(1 for r in rs if r['won'])/len(rs)*100) if rs else 0
print('entries (peak|lead|>=15): %d over %d days %s\n'%(len(rows),len(days),days))
print('%-8s %12s %12s %12s   | day total'%('day','|1h|0-15','|1h|15-40','|1h|40+'))
for dd in days:
    r=[x for x in rows if x['day']==dd]
    cells=[]
    for b in ('0-15','15-40','40+'):
        s=[x for x in r if x['band']==b]
        cells.append('%2.0f%%(n=%-3d)'%(wr(s),len(s)) if s else '  -      ')
    print('%-8s %12s %12s %12s   | %2.0f%% (n=%d)'%(dd,cells[0],cells[1],cells[2],wr(r),len(r)))
print('\nALL DAYS pooled:')
for b in ('0-15','15-40','40+'):
    s=[x for x in rows if x['band']==b]
    print('  |1h| %-5s : n=%-4d win=%2.0f%%'%(b,len(s),wr(s)))
keep=[x for x in rows if x['band']!='15-40']
print('\nBASELINE (take all entries):  n=%d win=%.1f%%'%(len(rows),wr(rows)))
print('GATE (skip |1h| 15-40):       n=%d win=%.1f%%  (skipped %d, those won %.1f%%)'%(
    len(keep),wr(keep),len(rows)-len(keep),wr([x for x in rows if x['band']=='15-40'])))
# OOS verdict: in how many days is 15-40 the worst band?
worstcnt=0; valid=0
for dd in days:
    r=[x for x in rows if x['day']==dd]
    bw={b:wr([x for x in r if x['band']==b]) for b in ('0-15','15-40','40+') if [x for x in r if x['band']==b]}
    if '15-40' in bw and len(bw)>=2:
        valid+=1
        if bw['15-40']==min(bw.values()): worstcnt+=1
print('\nOOS: |1h| 15-40 was the WORST-win-rate band in %d/%d days'%(worstcnt,valid))
