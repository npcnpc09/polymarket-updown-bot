"""Backtest stacking persist>=X and price-band filters ON TOP of max_lead>=15, btc/eth.
persist=|lead|/max_lead (momentum retained at entry). Tests whether these cut the faded/cheap losers
without killing PnL. Hold-to-settle, real-ask fill (DRY data)."""
import json
rows=[]
for l in open('data/multi_window_engine.jsonl',encoding='utf-8'):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if r.get('coin') not in ('btc','eth'): continue
    lead=r.get('lead'); ml=r.get('max_lead'); B=r.get('B')
    if lead is None or not ml or B is None: continue
    if ml<15: continue   # base filter
    rows.append({'persist':abs(lead)/ml,'B':B,'won':bool(r.get('won')),'pnl':r.get('pnl',0)})
def stat(sub,label):
    if not sub: print('%-34s (no trades)'%label); return
    n=len(sub); w=sum(1 for r in sub if r['won']); pnl=sum(r['pnl'] for r in sub)
    cost=sum(r['B']*5 for r in sub)
    print('%-34s n=%-4d win%%=%.0f%%  netPnL=%+7.2f  avg=%+.3f  margin=%+.1f%%'%(
        label,n,w/n*100,pnl,pnl/n,pnl/cost*100 if cost else 0))
print('base = max_lead>=15, btc/eth  (n=%d)\n'%len(rows))
stat(rows,'BASE (max_lead>=15)')
print('\n--- add PERSIST floor ---')
for p in (0.5,0.6,0.7):
    stat([r for r in rows if r['persist']>=p],'+ persist>=%.1f'%p)
print('\n--- add PRICE band (avoid cheap -EV coinflips) ---')
for lo in (0.5,0.55,0.6):
    stat([r for r in rows if r['B']>=lo],'+ B>=%.2f'%lo)
stat([r for r in rows if 0.55<=r['B']<=0.9],'+ B in [0.55,0.90]')
print('\n--- COMBINED persist>=0.6 AND B>=0.55 ---')
stat([r for r in rows if r['persist']>=0.6 and r['B']>=0.55],'persist>=0.6 & B>=0.55')
stat([r for r in rows if r['persist']>=0.6 and 0.55<=r['B']<=0.9],'persist>=0.6 & B in[0.55,0.90]')
