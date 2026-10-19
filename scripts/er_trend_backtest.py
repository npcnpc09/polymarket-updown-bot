"""Backtest ER-gated trend alignment. For each btc/eth 5m window: compute 1h Efficiency Ratio (ER)
+ 1h macro direction at entry; our side = leading side at entry (min3). Rule: when ER>=thr (sustained
trend) AND our side is COUNTER to macro -> SKIP. Does skipping remove losers in trend regimes WITHOUT
hurting chop days? Resolution = binance net (=Chainlink at >=5bps). Per-DAY (OOS)."""
import json,re,httpx,math,datetime,sys
from collections import defaultdict
NDAYS=int(sys.argv[1]) if len(sys.argv)>1 else 4
starts=defaultdict(set)
for ln in open('data/ce25_history_7d.jsonl',encoding='utf-8'):
    ln=ln.strip()
    if not ln: continue
    try: r=json.loads(ln)
    except: continue
    m=re.match(r'(btc|eth)-updown-5m-(\d+)',r.get('slug','') or '')
    if m: starts[m.group(1)].add(int(m.group(2)))
SYM={'btc':'BTCUSDT','eth':'ETHUSDT'}
allst=sorted(set().union(*starts.values())); cut=allst[-1]-NDAYS*86400
def bn(sym,t0,t1):
    out={}; cur=t0
    while cur<t1:
        r=httpx.get('https://api.binance.com/api/v3/klines',params={'symbol':sym,'interval':'1m','startTime':cur*1000,'endTime':t1*1000,'limit':1000},timeout=20).json()
        if not isinstance(r,list) or not r: break
        for k in r: out[int(k[0]//1000)]=float(k[4])
        cur=int(r[-1][0]//1000)+60
        if len(r)<1000: break
    return out
rows=[]
for c in SYM:
    ws=sorted(s for s in starts[c] if s>=cut)
    if not ws: continue
    d=bn(SYM[c],min(ws)-3700,max(ws)+360)
    def px(t):
        for dd in range(3):
            if t+dd in d: return d[t+dd]
        return None
    for st in ws:
        ent=st+180; op=px(st); pe=px(ent); cl=px(st+240)
        if not(op and pe and cl): continue
        # 1h ER + macro at entry
        p1=px(ent-3600)
        if not p1: continue
        net1h=math.log(pe/p1)*1e4
        path=0.0; prev=p1
        for mm in range(60):
            q=px(ent-3600+mm*60)
            if q: path+=abs(math.log(q/prev)*1e4); prev=q
        er=abs(net1h)/path if path>0 else 0
        macro='Up' if net1h>=0 else 'Down'
        lead=math.log(pe/op)*1e4; side='Up' if lead>=0 else 'Down'
        if abs(lead)<6: continue
        won=(side=='Up')==(cl>=op)
        rows.append({'day':datetime.datetime.utcfromtimestamp(st).strftime('%m-%d'),'er':er,'side':side,'macro':macro,'won':won,'counter':side!=macro})
days=sorted(set(r['day'] for r in rows))
print('windows: %d, days=%s\n'%(len(rows),days))
def wr(rs): return (sum(1 for r in rs if r['won'])/len(rs)*100) if rs else 0
print('BASELINE (bet leading side always): n=%d win=%.0f%% | per-day: %s'%(
    len(rows),wr(rows),{d:round(wr([r for r in rows if r['day']==d])) for d in days}))
print('\n--- counter-trend bets split by ER (are high-ER counter-trend bets the losers?) ---')
for lo,hi in ((0,0.3),(0.3,0.5),(0.5,1.01)):
    sub=[r for r in rows if r['counter'] and lo<=r['er']<hi]
    if sub: print('  counter-trend, ER %.1f-%.1f: n=%-3d win=%.0f%%'%(lo,hi,len(sub),wr(sub)))
wt=[r for r in rows if not r['counter']]
print('  WITH-trend (all ER): n=%-3d win=%.0f%%'%(len(wt),wr(wt)))
print('\n--- RULE: skip counter-trend when ER>=thr; per-day win% of KEPT trades ---')
for thr in (0.3,0.4,0.5):
    kept=[r for r in rows if not(r['counter'] and r['er']>=thr)]
    skipped=[r for r in rows if (r['counter'] and r['er']>=thr)]
    pd={d:round(wr([r for r in kept if r['day']==d])) for d in days}
    print('  ER>=%.1f: kept=%d win=%.0f%% (skipped %d, those won %.0f%%) | per-day kept: %s'%(
        thr,len(kept),wr(kept),len(skipped),wr(skipped),pd))
