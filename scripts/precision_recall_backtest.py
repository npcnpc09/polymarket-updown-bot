"""Precision/recall of entry TIMING x THRESHOLD over several days (btc/eth 5m).
Window list from ce25 log; underlying path + resolution from binance (net move; =Chainlink at >=5bps).
For each (entry_minute, lead_threshold): enter leading side at that minute if |lead|>=thr; win if that
side == net direction. Reports n_entered, win%, and RECALL of decisive-move (|net|>=20) winners captured."""
import json,re,httpx,math,sys
from collections import defaultdict
NDAYS=int(sys.argv[1]) if len(sys.argv)>1 else 3
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
    out={}; cur=t0
    while cur<t1:
        r=httpx.get('https://api.binance.com/api/v3/klines',params={'symbol':sym,'interval':'1m','startTime':cur*1000,'endTime':t1*1000,'limit':1000},timeout=20).json()
        if not isinstance(r,list) or not r: break
        for k in r: out[int(k[0]//1000)]=(float(k[1]),float(k[4]))
        cur=int(r[-1][0]//1000)+60
        if len(r)<1000: break
    return out
# restrict to last NDAYS of windows
allst=sorted(set().union(*starts.values()))
cut=allst[-1]-NDAYS*86400
wins={c:sorted(s for s in starts[c] if s>=cut) for c in starts}
print('windows: btc=%d eth=%d (last %d days)'%(len(wins['btc']),len(wins['eth']),NDAYS))
BN={}
for c in SYM:
    lo=min(wins[c])-120; hi=max(wins[c])+360
    BN[c]=bn(SYM[c],lo,hi)
    print('  binance %s: %d candles'%(c,len(BN[c])))
def px(c,t):
    for dd in range(3):
        if t+dd in BN[c]: return BN[c][t+dd]
    return None
# precompute per window: open, net direction, |net|, lead@min2/3/4
recs=[]
for c in wins:
    for st in wins[c]:
        o=px(c,st); cl=px(c,st+240)
        if not o or not cl: continue
        op=o[0]; net=math.log(cl[1]/op)*1e4
        leads={}
        for mm in (2,3,4):
            p=px(c,st+mm*60)
            leads[mm]=math.log(p[1]/op)*1e4 if p else None
        recs.append((c,op,net,leads))
decisive=[r for r in recs if abs(r[2])>=20]
print('\ntotal windows=%d  | decisive-move(|net|>=20) winners=%d\n'%(len(recs),len(decisive)))
print('%-18s%8s%7s%9s%9s'%('config','nEnter','win%','recall%','margin~'))
for em in (2,3,4):
    for thr in (6,10,15):
        ent=[r for r in recs if r[3][em] is not None and abs(r[3][em])>=thr]
        if not ent: continue
        won=[r for r in ent if (r[3][em]>=0)==(r[2]>=0)]
        # recall of decisive winners
        capd=[r for r in decisive if r[3][em] is not None and abs(r[3][em])>=thr and (r[3][em]>=0)==(r[2]>=0)]
        rec=len(capd)/len(decisive)*100 if decisive else 0
        # crude margin: win at avg payoff ~ depends on price; proxy = win% - 50 (vs coinflip) is misleading;
        # use simple per-trade: assume entry priced at implied = win-rate-of-bucket... skip, show win% + recall
        print('min%d lead>=%-2d    %8d%6.0f%%%8.0f%%'%(em,thr,len(ent),len(won)/len(ent)*100,rec))
print('\n(current strategy ~ min3 lead>=6. Earlier/looser = higher recall, watch win%% drop.)')
