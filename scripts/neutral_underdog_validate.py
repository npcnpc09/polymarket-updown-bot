"""GATE for 'can we scale ce25's longshot harvest': is 'cheap underdog AGAINST the binance lead' +EV for the
WHOLE MARKET (all traders), or just ce25's selection? Fetch ALL-trader BUY trades (data-api /trades) for
many windows, filter underdog (<0.5), reconstruct binance lead toward the bought side at the fill timestamp,
bucket by lead-toward-side x price -> win% vs price (favorite-longshot test). If the cheap longshot band
wins MORE than its price implies neutrally -> a RAW harvestable edge (scalable). If ~breakeven -> ce25's
selection (not replicable by spraying)."""
import httpx,math,statistics,time
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
wins=dict(list(wins.items())[:90])
print("全市场中性验证: %d个窗口\n"%len(wins))
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
    if not aa:return None
    return aa[0]+((bb[0]-aa[0])*((t-lo)/60.0) if bb else 0)
B=[]
for slug,(cid,coin,dur,st) in wins.items():
    o=KL[coin].get(st);cl=KL[coin].get(st+DUR[dur])
    if not o or not cl: continue
    win="Up" if cl[1]>=o[0] else "Down"; op=o[0]
    try: trs=c.get("https://data-api.polymarket.com/trades",params={"market":cid,"limit":1000}).json()
    except: continue
    if not isinstance(trs,list): continue
    for t in trs:
        if (t.get("side") or "").upper()!="BUY": continue
        p=t.get("price") or 0; oc=t.get("outcome"); sz=t.get("size") or 0; ts=t.get("timestamp")
        if not(0<p<0.5) or oc not in ("Up","Down") or not ts or ts<st or ts>st+DUR[dur]: continue
        bp=pxat(coin,int(ts))
        if not bp: continue
        lead=math.log(bp/op)*1e4*(1 if oc=="Up" else -1)  # toward bought side
        B.append({"price":p,"won":(oc==win),"size":sz,"lead":lead,"off":ts-st})
print("全市场 underdog(<0.5) BUY: %d笔\n"%len(B))
def stat(rs,lbl):
    if not rs: print("  %-22s n=0"%lbl);return
    wr=sum(1 for t in rs if t["won"])/len(rs); ap=statistics.mean(t["price"] for t in rs)
    cost=sum(t["size"]*t["price"] for t in rs); pf=sum((t["size"]*(1-t["price"]) if t["won"] else -t["size"]*t["price"]) for t in rs)
    print("  %-22s n=%-5d 实胜%2.0f%% 均价%.2f 错价%+.0fpp ROI%+6.1f%%"%(lbl,len(rs),wr*100,ap,(wr-ap)*100,pf/cost*100 if cost else 0))
print("=== 中性: 便宜underdog 按 binance领先(朝买的侧) — 错价>0=被低估=可收割 ===")
stat([t for t in B if t["lead"]<-8],"强反向<-8 (深longshot)")
stat([t for t in B if -8<=t["lead"]<-2],"弱反向 -8~-2")
stat([t for t in B if -2<=t["lead"]<2],"中性 -2~2")
stat([t for t in B if t["lead"]>=2],"同向 >=2")
print("\n=== 中性: lead反它(<0) 按价格档 (vs ce25的+44.7%) ===")
ag=[t for t in B if t["lead"]<0]
for lo,hi,l in ((0,0.2,"<0.2"),(0.2,0.3,"0.2-0.3"),(0.3,0.4,"0.3-0.4"),(0.4,0.5,"0.4-0.5")):
    stat([t for t in ag if lo<=t["price"]<hi],"lead反它 "+l)
print("\n判据: 若中性下 错价稳>0(尤其0.2-0.4)→ 原始band真低估=可放大; 若≈0 → 是ce25选择, 放大无用")
