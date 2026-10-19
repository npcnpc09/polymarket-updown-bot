"""Validate the cheap-longshot edge for SCALE: (1) OOS — split the neutral underdog trades into time-halves,
does the underpricing hold in BOTH? (2) Scale Monte-Carlo — resample real underdog trades into a diversified
sequential portfolio; measure return, max drawdown, ruin prob. Does diversification actually HARVEST the
28%-win +EV, or does the variance kill you? Caveat printed: binance-reconstructed winner (settlement-source
risk) — a real-money tiny probe is the only true test, this bounds whether it's even worth one."""
import httpx,math,statistics,time,random
random.seed(0)
from collections import defaultdict
CE="0xcE25E214D5cfE4f459cf67F08DF581885AAE7Fdc"
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
A=[]
for off in range(0,2500,500):
    try: a=c.get("https://data-api.polymarket.com/activity",params={"user":CE,"limit":500,"offset":off}).json()
    except: break
    if not isinstance(a,list) or not a: break
    A+=[x for x in a if x.get("type")=="TRADE" and x.get("conditionId")]
    if len(a)<500: break
SYM={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT","xrp":"XRPUSDT","doge":"DOGEUSDT"}; DUR={"5m":300,"15m":900}
now=int(time.time()); wins={}
for x in A:
    s=x.get("slug","");parts=s.split("-")
    if "updown" not in s or len(parts)<4: continue
    coin=parts[0];dur=next((d for d in DUR if f"-{d}-" in s),None)
    if coin not in SYM or not dur: continue
    try: st=int(parts[-1])
    except: continue
    if st+DUR[dur]>now-30: continue
    wins[s]=(x["conditionId"],coin,dur,st)
wins=dict(sorted(wins.items(),key=lambda kv:kv[1][3])[:90])  # chronological
need=set(v[1] for v in wins.values());KL={}
for coin in need:
    sts=[v[3] for v in wins.values() if v[1]==coin]
    out={};cur=min(sts)-180;hi=max(v[3]+DUR[v[2]] for v in wins.values() if v[1]==coin)+300
    while cur<hi:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[4]))
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    KL[coin]=out
def pxat(coin,t):
    d=KL[coin];lo=(t//60)*60;aa=d.get(lo);bb=d.get(lo+60)
    return (aa[0]+((bb[0]-aa[0])*((t-lo)/60.0) if bb else 0)) if aa else None
# collect underdog trades in band 0.15-0.4 with lead AGAINST (the +EV cell), in chronological window order
trades=[]
order=sorted(wins.items(),key=lambda kv:kv[1][3])
for i,(slug,(cid,coin,dur,st)) in enumerate(order):
    o=KL[coin].get(st);cl=KL[coin].get(st+DUR[dur])
    if not o or not cl: continue
    win="Up" if cl[1]>=o[0] else "Down"; op=o[0]
    try: trs=c.get("https://data-api.polymarket.com/trades",params={"market":cid,"limit":1000}).json()
    except: continue
    if not isinstance(trs,list): continue
    for t in trs:
        if (t.get("side") or "").upper()!="BUY": continue
        p=t.get("price") or 0; oc=t.get("outcome"); ts=t.get("timestamp")
        if not(0.15<=p<0.4) or oc not in ("Up","Down") or not ts or ts<st or ts>st+DUR[dur]: continue
        bp=pxat(coin,int(ts))
        if not bp: continue
        lead=math.log(bp/op)*1e4*(1 if oc=="Up" else -1)
        if lead>=0: continue  # AGAINST the lead = the cheap cell
        trades.append({"price":p,"won":(oc==win),"half":0 if i<len(order)//2 else 1})
print("候选成交(0.15-0.4, lead反它): %d笔\n"%len(trades))
def ev(rs):
    if not rs: return None
    wr=sum(1 for t in rs if t["won"])/len(rs); ap=statistics.mean(t["price"] for t in rs)
    perdollar=statistics.mean(((1-t["price"])/t["price"] if t["won"] else -1) for t in rs)  # return per $1 staked
    return wr,ap,perdollar
print("=== OOS: 前半 vs 后半 (错价稳不稳) ===")
for h,nm in ((0,"前半"),(1,"后半")):
    e=ev([t for t in trades if t["half"]==h])
    if e: print("  %s n=%-4d 胜%2.0f%% 均价%.2f 每$EV%+.3f 错价%+.0fpp"%(nm,len([t for t in trades if t['half']==h]),e[0]*100,e[1],e[2],(e[0]-e[1])*100))
print("\n=== Scale 蒙特卡洛: 分散组合能否收割这个高方差edge ===")
pool=trades
def mc(bankroll,betfrac,N,K=3000):
    """K paths: start=bankroll, each window bet betfrac*bankroll on 1 resampled longshot (flat-ish), N windows."""
    rets=[]; ruin=0; dds=[]
    for _ in range(K):
        eq=bankroll; peak=bankroll; mdd=0
        for _ in range(N):
            t=pool[random.randrange(len(pool))]
            stake=betfrac*bankroll  # fixed fraction of STARTING bankroll (flat)
            eq+= stake*((1-t["price"])/t["price"]) if t["won"] else -stake
            if eq>peak: peak=eq
            if peak-eq>mdd: mdd=peak-eq
            if eq<=0: ruin+=1; break
        rets.append(eq/bankroll-1); dds.append(mdd/bankroll)
    rets.sort()
    return statistics.median(rets)*100, rets[int(K*.1)]*100, statistics.median(dds)*100, ruin/K*100
print("  (每窗下 起始本金的betfrac, flat, N窗后)")
print("  %-22s 中位收益 p10收益 中位回撤 破产率"%"配置")
for bf in (0.02,0.05,0.10):
    for N in (100,500):
        med,p10,dd,ru=mc(1000,bf,N)
        print("  下注%2.0f%% × %3d窗      %+6.1f%%  %+6.1f%%  %5.1f%%  %5.1f%%"%(bf*100,N,med,p10,dd,ru))
print("\n判据: 若中位收益稳>0 且 破产率≈0 且 p10(差运气)不爆 → 分散能收割, 值得真钱tiny probe验结算源.")
print("注: binance重建胜负 — 若实为结算源artifact, 真钱probe会立刻暴露(真实胜率远低于这里).")
