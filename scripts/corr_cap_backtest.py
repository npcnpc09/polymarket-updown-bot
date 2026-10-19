"""Backtest a NET-SAME-DIRECTION concurrency cap on btc/eth multi-window DRY data.
The current cap (MAX_PER_COIN=2) limits same-COIN concurrency but btc+eth move together, so
'btc Down + eth Down + btc Down' (3 correlated Down bets) passes it. This tests capping concurrent
SAME-DIRECTION positions (the real correlated-reversal risk) — does it cut drawdown without killing PnL?"""
import json,datetime
LATE=180  # entry ~3min into the 5m window
cands=[]
for l in open('data/multi_window_engine.jsonl',encoding='utf-8'):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    try: st=int(r.get('slug','').split('-')[-1])
    except: continue
    if r.get('coin') not in ('btc','eth'): continue
    if (r.get('max_lead') or 0)<15: continue   # our actual entry filter
    cands.append({'entry':st+LATE,'settle':st+300,'coin':r.get('coin'),'side':r.get('side'),
                  'pnl':r.get('pnl',0),'won':bool(r.get('won'))})
cands.sort(key=lambda x:x['entry'])
def sim(cap_mode,cap):
    # cap_mode: 'none' | 'percoin' | 'perdir' (max concurrent same-direction)
    openpos=[]; realized=0.0; peak=0.0; mdd=0.0; taken=[]
    for c in cands:
        t=c['entry']
        # settle finished positions
        still=[]
        for p in openpos:
            if p['settle']<=t: realized+=p['pnl']; peak=max(peak,realized); mdd=max(mdd,peak-realized)
            else: still.append(p)
        openpos=still
        # apply cap
        ok=True
        if cap_mode=='percoin':
            if sum(1 for p in openpos if p['coin']==c['coin'])>=cap: ok=False
        elif cap_mode=='perdir':
            if sum(1 for p in openpos if p['side']==c['side'])>=cap: ok=False
        if ok: openpos.append(c); taken.append(c)
    for p in openpos: realized+=p['pnl']; peak=max(peak,realized); mdd=max(mdd,peak-realized)
    n=len(taken); w=sum(1 for c in taken if c['won'])
    return n,w,realized,mdd
print('candidate btc/eth max_lead>=15 windows: %d\n'%len(cands))
print('%-26s%6s%6s%9s%9s%9s'%('cap','n','win%','netPnL','maxDD','PnL/DD'))
for lab,mode,cap in (('UNLIMITED','none',0),('per-coin<=2 (current)','percoin',2),
                     ('per-DIR<=3','perdir',3),('per-DIR<=2 (proposed)','perdir',2),('per-DIR<=1','perdir',1)):
    n,w,pnl,dd=sim(mode,cap)
    ratio=pnl/dd if dd>0 else float('inf')
    print('%-26s%6d%5.0f%%%+9.2f%9.2f%9.2f'%(lab,n,w/n*100 if n else 0,pnl,-dd,ratio))
print('\nPnL/DD = return per unit drawdown (higher = better risk-adjusted)')
