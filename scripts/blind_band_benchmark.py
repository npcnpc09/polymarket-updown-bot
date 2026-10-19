"""BLIND band benchmark — is each price band +EV for ANYONE (favorite-longshot bias, replicable) or only for
ce25 (his selection)? Pull ALL-trader BUY trades over many settled updown windows, winner via binance (reliable
on the EXTREME bands where the move is decisive), bucket EVERY buy by PRICE band -> blind win% vs price + ROI.
Compare to profit_cells.py (ce25's own fills). If blind win% ~= price (calibrated) but ce25's > price, the
band edge is his SELECTION (not replicable blind). If blind win% > price, the BAND itself pays (replicable)."""
import httpx,math,statistics,time,sys
from collections import defaultdict
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
CE="0xcE25E214D5cfE4f459cf67F08DF581885AAE7Fdc"
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
A=[]
for off in range(0,4000,500):
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
wins=dict(list(wins.items())[:160])
print("取 %d 个已结算窗口的\033[1m全市场\033[0m成交...\n"%len(wins))
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
B=[]
for slug,(cid,coin,dur,st) in wins.items():
    o=KL[coin].get(st);cl=KL[coin].get(st+DUR[dur])
    if not o or not cl: continue
    win="Up" if cl[1]>=o[0] else "Down"
    try: trs=c.get("https://data-api.polymarket.com/trades",params={"market":cid,"limit":1000}).json()
    except: continue
    if not isinstance(trs,list): continue
    for t in trs:
        if (t.get("side") or "").upper()!="BUY": continue
        p=t.get("price") or 0; oc=t.get("outcome"); sz=t.get("size") or 0
        if not (0<p<1) or oc not in ("Up","Down") or sz<=0: continue
        B.append({"price":p,"won":(oc==win),"size":sz})
print("全市场BUY: %d笔, %d窗\n"%(len(B),len(wins)))
BANDS=[(0,0.1),(0.1,0.2),(0.2,0.3),(0.3,0.4),(0.4,0.5),(0.5,0.6),(0.6,0.7),(0.7,0.8),(0.8,0.9),(0.9,1.01)]
print("%-10s %7s %7s %6s %8s %8s  %s"%("价格档","笔数","均价","盲胜%","win%-价","盲ROI","判定"))
for lo,hi in BANDS:
    rs=[t for t in B if lo<=t["price"]<hi]
    if not rs: continue
    wr=sum(1 for t in rs if t["won"])/len(rs)*100; ap=statistics.mean(t["price"] for t in rs)
    sp=sum(t["size"]*t["price"] for t in rs); pf=sum((t["size"]*(1-t["price"]) if t["won"] else -t["size"]*t["price"]) for t in rs)
    roi=pf/sp*100 if sp else 0; edge=wr-ap*100
    flag="\033[1m带+EV(可复制)\033[0m" if edge>2 else ("带亏" if edge<-2 else "校准≈0")
    print("%4.1f-%-4.1f %7d %6.3f %5.0f%% %+6.0fpp %+7.1f%%  %s"%(lo,hi,len(rs),ap,wr,edge,roi,flag))
print("\n对比 profit_cells(ce25自己): 若某档这里'校准≈0'但他那里'档+EV' => 那是他的\033[1m选股\033[0m, 盲买拿不到.")
print("若这里也'带+EV' => 真实favorite-longshot带偏差, 我们盲买/用信号就能复制. (binance赢家, 极端档可靠)")
