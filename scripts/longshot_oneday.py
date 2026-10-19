"""ONE-DAY backtest of ce25's cheap-underdog strategy on the recent ~day of windows: real all-trader fill
prices + binance-reconstructed outcomes. Simulate $1000 buying the cheap-underdog side each window,
diversified. Report day PnL/ROI by sub-band. CAVEAT printed loud: cheap-band outcomes are binance-inflated
(the artifact) — this is an OPTIMISTIC mirage, real settlement would be far lower. Shown only because the
user asked to see the one-day number; it does NOT escape the reconstruction artifact."""
import httpx,math,statistics,time
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
CE="0xcE25E214D5cfE4f459cf67F08DF581885AAE7Fdc"
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
wins=dict(list(wins.items())[:120])
span=(max(v[3] for v in wins.values())-min(v[3] for v in wins.values()))/3600
print("窗口 %d (跨~%.1fh, 当~一天的近端样本)\n"%(len(wins),span))
need=set(v[1] for v in wins.values());KL={}
for coin in need:
    sts=[v[3] for v in wins.values() if v[1]==coin]
    out={};cur=min(sts)-120;hi=max(v[3]+DUR[v[2]] for v in wins.values() if v[1]==coin)+300
    while cur<hi:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[4]))
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    KL[coin]=out
# simulate: in each window, buy every all-trader cheap-underdog fill we'd mimic (price 0.2-0.4), $5 each
BET=5.0; rows=[]
for slug,(cid,coin,dur,st) in wins.items():
    o=KL[coin].get(st);cl=KL[coin].get(st+DUR[dur])
    if not o or not cl: continue
    win="Up" if cl[1]>=o[0] else "Down"
    try: trs=c.get("https://data-api.polymarket.com/trades",params={"market":cid,"limit":1000}).json()
    except: continue
    if not isinstance(trs,list): continue
    seen=set()
    for t in trs:
        if (t.get("side") or "").upper()!="BUY": continue
        p=t.get("price") or 0; oc=t.get("outcome")
        if not(0.2<=p<0.4) or oc not in ("Up","Down"): continue
        key=(slug,oc,round(p,2))
        if key in seen: continue
        seen.add(key)  # dedup so one window doesn't dominate
        shares=BET/p; won=(oc==win)
        rows.append({"price":p,"won":won,"pnl":shares*(1-p) if won else -shares*p,"cost":BET})
def band(rs,lbl):
    if not rs: return
    cost=sum(r["cost"] for r in rs); pf=sum(r["pnl"] for r in rs)
    print("  %-10s n=%-4d 胜%2.0f%% 投入$%5.0f 盈亏$%+7.1f ROI%+6.1f%%"%(lbl,len(rs),sum(1 for r in rs if r["won"])/len(rs)*100,cost,pf,pf/cost*100 if cost else 0))
print("=== 一天回测: 买便宜underdog(0.2-0.4), 每注$%g, 分散 ==="%BET)
band(rows,"全部0.2-0.4")
band([r for r in rows if r["price"]<0.3],"0.2-0.3")
band([r for r in rows if r["price"]>=0.3],"0.3-0.4")
tot_pf=sum(r["pnl"] for r in rows); tot_cost=sum(r["cost"] for r in rows)
print("\n  >>> 一天合计: 投入$%.0f 盈亏$%+.1f ROI%+.1f%% (%d笔)"%(tot_cost,tot_pf,tot_pf/tot_cost*100 if tot_cost else 0,len(rows)))
print("\n*** 警告: 胜负用binance重建, 在0.2-0.4这个near-coinflip带系统性灌水(~7x). ***")
print("*** 这个+ROI是海市蜃楼; 真实Chainlink结算下会低得多, 可能≈0. 不是可上规模的依据. ***")
