"""Can WE (taker, paying the REAL fill price) profit from ce25's lead-selection? Use ALL-trader BUY trades
(= real taker-accessible prices, not ce25's possibly-cheaper fills, not a reconstructed price model). For
each BUY: reconstruct binance lead toward the bought side AT the trade's timestamp. Bucket by lead x price,
compute win% and EV at the REAL price paid. If lead-aligned sides are still +EV at real prices -> taker
strategy works; if priced-in (win% ~= price) -> it's the same thin-edge wall as our z-maker."""
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
now=int(time.time())
wins={}
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
print("取 %d 个已结算窗口的全市场成交\n"%len(wins))
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
        if p<=0 or oc not in ("Up","Down") or not ts: continue
        if ts<st or ts>st+DUR[dur]: continue
        bp=pxat(coin,int(ts))
        if not bp: continue
        lead=math.log(bp/op)*1e4*(1 if oc=="Up" else -1)
        B.append({"price":p,"won":(oc==win),"size":sz,"lead":lead,"off":ts-st})
print("全市场BUY(有时间戳,可定lead): %d笔\n"%len(B))
def stat(rs):
    if not rs: return None
    wr=sum(1 for t in rs if t["won"])/len(rs); ap=statistics.mean(t["price"] for t in rs)
    sp=sum(t["size"]*t["price"] for t in rs); pf=sum((t["size"]*(1-t["price"]) if t["won"] else -t["size"]*t["price"]) for t in rs)
    return len(rs),wr,ap,wr-ap,pf/sp*100 if sp else 0
print("=== 真实价下, 按 标的领先(朝买的侧) 的 win-vs-price ===")
for llo,lhi,l in ((-99,-8,"领先<-8"),(-8,-2,"-8~-2"),(-2,2,"-2~2"),(2,8,"2~8"),(8,15,"8~15"),(15,99,">=15")):
    s=stat([t for t in B if llo<=t["lead"]<lhi])
    if s: print("  %-9s n=%-5d 实胜%2.0f%% 真实均价%.3f 错价%+.0fpp ROI%+5.1f%%"%(l,s[0],s[1]*100,s[2],s[3]*100,s[4]))
print("\n=== 只看 lead>=8 (强同向) × 价格档: 真实价还有没有edge ===")
strong=[t for t in B if t["lead"]>=8]
for lo,hi,l in ((0,0.5,"<0.5便宜"),(0.5,0.65,"0.5-0.65"),(0.65,0.75,"0.65-0.75"),(0.75,0.85,"0.75-0.85"),(0.85,1.01,">=0.85")):
    s=stat([t for t in strong if lo<=t["price"]<hi])
    if s: print("  lead>=8 %-9s n=%-4d 实胜%2.0f%% 真实均价%.3f 错价%+.0fpp ROI%+5.1f%%"%(l,s[0],s[1]*100,s[2],s[3]*100,s[4]))
print("\n=== lead>=8 × 入场时点(越早价越便宜?): 真实价 ===")
for lo,hi,l in ((0,60,"<60s"),(60,150,"60-150s"),(150,300,"150-300s")):
    s=stat([t for t in strong if lo<=t["off"]<hi])
    if s: print("  lead>=8 %-9s n=%-4d 实胜%2.0f%% 真实均价%.3f 错价%+.0fpp ROI%+5.1f%%"%(l,s[0],s[1]*100,s[2],s[3]*100,s[4]))
