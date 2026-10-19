"""NEUTRAL favorite-longshot test: fetch ALL traders' BUY trades (data-api /trades?market=cid) for many
recent settled windows (cids from ce25's activity), bucket by price, win-vs-price. Removes ce25's
selection bias -> is the mid-band (0.25-0.5) underpriced for the WHOLE MARKET, not just ce25?"""
import httpx,json,math,statistics,time,datetime
from collections import defaultdict
CE="0xcE25E214D5cfE4f459cf67F08DF581885AAE7Fdc"
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
# get recent window (slug,cid) from ce25 activity
A=[]
for off in range(0,2500,500):
    try: a=c.get("https://data-api.polymarket.com/activity",params={"user":CE,"limit":500,"offset":off}).json()
    except: break
    if not isinstance(a,list) or not a: break
    A+=[x for x in a if x.get("type")=="TRADE" and x.get("conditionId")]
    if len(a)<500: break
SYM={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT","xrp":"XRPUSDT","doge":"DOGEUSDT"}; DUR={"5m":300,"15m":900}
now=int(time.time())
wins={}  # slug -> (cid, coin, dur, st)
for x in A:
    s=x.get("slug","");parts=s.split("-")
    if "updown" not in s or len(parts)<4: continue
    coin=parts[0];dur=next((d for d in DUR if f"-{d}-" in s),None)
    if coin not in SYM or not dur: continue
    try: st=int(parts[-1])
    except: continue
    if st+DUR[dur]>now-30: continue
    wins[s]=(x["conditionId"],coin,dur,st)
wins=dict(list(wins.items())[:70])   # cap windows (each /trades call)
print("取 %d 个已结算窗口的全市场成交\n"%len(wins))
# binance winners
need=set(v[1] for v in wins.values());KL={}
sts=[v[3] for v in wins.values()]
for coin in need:
    out={};cur=min(sts)-120;hi=max(v[3]+DUR[v[2]] for v in wins.values() if v[1]==coin)+300
    while cur<hi:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[4]))
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    KL[coin]=out
def winner(coin,st,dur):
    d=KL.get(coin,{});o=d.get(st);cl=d.get(st+DUR[dur])
    if not o or not cl: return None
    return "Up" if cl[1]>=o[0] else "Down"
# fetch all-trader BUY trades per window
allbuys=[]
for slug,(cid,coin,dur,st) in wins.items():
    win=winner(coin,st,dur)
    if not win: continue
    try: trs=c.get("https://data-api.polymarket.com/trades",params={"market":cid,"limit":1000}).json()
    except: continue
    if not isinstance(trs,list): continue
    for t in trs:
        if (t.get("side") or "").upper()!="BUY": continue
        p=t.get("price") or 0; oc=t.get("outcome"); sz=t.get("size") or 0
        if p<=0 or oc not in ("Up","Down"): continue
        allbuys.append({"price":p,"won":(oc==win),"size":sz})
print("全市场BUY成交: %d笔 (所有交易者)\n"%len(allbuys))
BANDS=[(0,0.25,"<0.25"),(0.25,0.4,"0.25-0.4"),(0.4,0.5,"0.4-0.5"),(0.5,0.7,"0.5-0.7"),(0.7,1.01,">=0.7")]
print("=== 全市场 各价格档: 实际胜率 vs 价格 = 错价 ===")
for lo,hi,l in BANDS:
    rs=[t for t in allbuys if lo<=t["price"]<hi]
    if not rs: print("  %-10s n=0"%l); continue
    wr=sum(1 for t in rs if t["won"])/len(rs); ap=statistics.mean(t["price"] for t in rs)
    sp=sum(t["size"]*t["price"] for t in rs); pf=sum((t["size"]*(1-t["price"]) if t["won"] else -t["size"]*t["price"]) for t in rs)
    print("  %-10s n=%-5d 实胜%2.0f%% 均价%.2f 错价%+.0fpp ROI%+5.1f%%"%(l,len(rs),wr*100,ap,(wr-ap)*100,pf/sp*100 if sp else 0))
