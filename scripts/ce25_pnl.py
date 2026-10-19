"""ce25 recent PnL: pull his BUY trades, reconstruct each window's winner from binance (open@st vs
close@st+dur), and compute per-trade profit (win: size*(1-price), loss: -size*price). Is he actually
profitable in recent hours? Breakdown by coin / duration / favorite-vs-underdog."""
import httpx,json,math,statistics,time,datetime
from collections import defaultdict
CE="0xcE25E214D5cfE4f459cf67F08DF581885AAE7Fdc"
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
A=[]
for off in range(0,3000,500):
    try: a=c.get("https://data-api.polymarket.com/activity",params={"user":CE,"limit":500,"offset":off}).json()
    except: break
    if not isinstance(a,list) or not a: break
    A+=[x for x in a if x.get("type")=="TRADE" and (x.get("side") or "").upper()=="BUY"]
    if len(a)<500: break
SYM={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT","xrp":"XRPUSDT","doge":"DOGEUSDT"}
DUR={"5m":300,"15m":900}
now=int(time.time())
# parse trades
trades=[]
for x in A:
    s=x.get("slug","")
    parts=s.split("-")
    if len(parts)<4 or "updown" not in s: continue
    coin=parts[0]; dur=None
    for dk in DUR:
        if f"-{dk}-" in s: dur=dk
    if coin not in SYM or not dur: continue
    try: st=int(parts[-1])
    except: continue
    if st+DUR[dur]>now-30: continue   # settled only
    trades.append({"coin":coin,"dur":dur,"st":st,"side":x.get("outcome"),"price":x.get("price") or 0,"size":x.get("size") or 0})
print("ce25 已结算的BUY: %d笔"%len(trades))
if not trades: raise SystemExit
sts=[t["st"] for t in trades]
# fetch binance per coin
need=set(t["coin"] for t in trades)
KL={}
for coin in need:
    out={};cur=min(sts)-120
    hi=max(t["st"]+DUR[t["dur"]] for t in trades if t["coin"]==coin)+300
    while cur<hi:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[4]))
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    KL[coin]=out
def winner(t):
    d=KL.get(t["coin"],{}); o=d.get(t["st"]); cl=d.get(t["st"]+DUR[t["dur"]]) or d.get(t["st"]+DUR[t["dur"]]-60)
    if not o or not cl: return None
    return "Up" if cl[1]>=o[0] else "Down"
tot=0.0; nw=0; n=0; byc=defaultdict(lambda:[0.0,0,0]); fav=[0.0,0,0]; und=[0.0,0,0]; spent=0.0
for t in trades:
    win=winner(t)
    if win is None: continue
    won=(t["side"]==win); p=t["price"]; sz=t["size"]
    profit=sz*(1-p) if won else -sz*p
    tot+=profit; spent+=sz*p; n+=1; nw+=1 if won else 0
    byc[t["coin"]][0]+=profit; byc[t["coin"]][1]+=1; byc[t["coin"]][2]+=1 if won else 0
    tgt=fav if p>=0.5 else und  # 买的是favorite(>=0.5)还是underdog(<0.5)
    tgt[0]+=profit; tgt[1]+=1; tgt[2]+=1 if won else 0
print("可定胜负: %d笔, 时间 %s~%s"%(n,datetime.datetime.utcfromtimestamp(min(sts)).strftime("%m-%d %H:%M"),datetime.datetime.utcfromtimestamp(max(sts)).strftime("%H:%M")))
print("\n=== ce25 真实盈亏(重建) ===")
print("  总盈亏 $%+.1f | 投入$%.0f | ROI %+.1f%% | 胜率 %.0f%%"%(tot,spent,tot/spent*100 if spent else 0,nw/n*100 if n else 0))
print("\n=== 买favorite(>=0.5) vs underdog(<0.5) ===")
print("  favorite: n=%-4d 胜%2.0f%% 盈亏$%+.1f"%(fav[1],fav[2]/fav[1]*100 if fav[1] else 0,fav[0]))
print("  underdog: n=%-4d 胜%2.0f%% 盈亏$%+.1f"%(und[1],und[2]/und[1]*100 if und[1] else 0,und[0]))
print("\n=== 按币 ===")
for coin,(pf,cn,cw) in sorted(byc.items(),key=lambda x:-x[1][0]):
    print("  %-4s n=%-4d 胜%2.0f%% 盈亏$%+.1f"%(coin,cn,cw/cn*100 if cn else 0,pf))
