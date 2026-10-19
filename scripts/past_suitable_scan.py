"""Scan past 7 days: when was BTC vol < VOL_OK (the maker's 'suitable to open' condition), how much of
the time, and which time blocks. Validate: did our reconstructed win rate actually run higher in the
low-vol (suitable) periods? Pure binance."""
import math,httpx,statistics,time,datetime
VOL_OK=5.0
NOW=int(time.time()); LO=NOW-7*86400-300
c=httpx.Client(timeout=30,headers={"User-Agent":"Mozilla/5.0"})
def fetch(sym):
    out={};cur=LO
    while cur<NOW:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":NOW*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[4]))   # open, close
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
BTC=fetch("BTCUSDT")
def vol30(t):
    cl=[BTC.get(t-60*i) for i in range(31)]; cl=[x[1] for x in cl if x]
    if len(cl)<20: return None
    return statistics.pstdev([math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))])
# sample every 15 min -> suitable blocks
samples=[]
t=int(LO//900)*900+1800
while t<NOW:
    v=vol30(t)
    if v is not None: samples.append((t,v))
    t+=900
suit=[s for s in samples if s[1]<VOL_OK]
print("过去7天: 每15分钟采样 %d 点, 其中 vol<%.1f 的: %d (%.0f%%时间适合)\n"%(len(samples),VOL_OK,len(suit),len(suit)/len(samples)*100))
# 连续适合时段
print("=== 适合时段(vol<%.1f 连续块, >=30min) ==="%VOL_OK)
blocks=[]; cur=None
for tm,v in samples:
    if v<VOL_OK:
        if cur is None: cur=[tm,tm]
        else: cur[1]=tm
    else:
        if cur: blocks.append(tuple(cur)); cur=None
if cur: blocks.append(tuple(cur))
for a,b in blocks:
    dur=(b-a)/3600
    if dur>=0.5:
        print("  %s ~ %s (%.1fh)"%(datetime.datetime.utcfromtimestamp(a).strftime("%m-%d %H:%M"),datetime.datetime.utcfromtimestamp(b+900).strftime("%H:%M"),dur))
# 逐天适合小时占比
print("\n=== 逐天 vol<%.1f 的小时占比 ==="%VOL_OK)
from collections import defaultdict
byday=defaultdict(lambda:[0,0])
for tm,v in samples:
    d=datetime.datetime.utcfromtimestamp(tm).strftime("%m-%d"); byday[d][0]+=1; byday[d][1]+=(1 if v<VOL_OK else 0)
for d in sorted(byday): tot,s=byday[d]; print("  %s: 适合 %.0f%% (%d/%d 个15min)"%(d,s/tot*100,s,tot))
# 验证: 低vol vs 高vol 的重建胜率
print("\n=== 验证: 重建胜率 (|lead|>=8 窗口) ===")
def o(t): v=BTC.get(t); return v[0] if v else None
def cl(t): v=BTC.get(t); return v[1] if v else None
lo_w=[0,0]; hi_w=[0,0]
for st in range(int(LO//300)*300,NOW-300,300):
    op=o(st); p120=cl(st+120); p180=cl(st+180); clo=cl(st+300); v=vol30(st)
    if None in (op,p120,p180,clo) or v is None: continue
    lead=(math.log(p120/op)+math.log(p180/op))/2*1e4
    if abs(lead)<8: continue
    won=(lead>=0 and clo>=op) or (lead<0 and clo<op)
    tgt=lo_w if v<VOL_OK else hi_w; tgt[0]+=1; tgt[1]+=(1 if won else 0)
print("  vol<%.1f (适合): n=%d 胜%.0f%%"%(VOL_OK,lo_w[0],lo_w[1]/lo_w[0]*100 if lo_w[0] else 0))
print("  vol>=%.1f:        n=%d 胜%.0f%%"%(VOL_OK,hi_w[0],hi_w[1]/hi_w[0]*100 if hi_w[0] else 0))
