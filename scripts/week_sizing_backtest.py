"""Backtest value-weighted sizing (bet heavy on high-conviction = high z) vs fixed size, over 1 week of
z>=2.5 windows. KEY: report not just total PnL but MAX DRAWDOWN and WORST single loss — the value-weight
risk is concentrated tail loss (we lack eebde's diversification). Price is MODELED from lead (taker-ish;
maker would be cheaper so real PnL better, but the fixed-vs-weighted RISK comparison is what matters)."""
import math,httpx,statistics,time
NOW=int(time.time()); LO=NOW-7*86400-300
c=httpx.Client(timeout=30,headers={"User-Agent":"Mozilla/5.0"})
def fetch(sym):
    out={};cur=LO
    while cur<NOW:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":NOW*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=float(x[1])
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
PX={"btc":fetch("BTCUSDT"),"eth":fetch("ETHUSDT")}
print("币安分钟: btc=%d eth=%d\n"%(len(PX["btc"]),len(PX["eth"])))
def price_model(lead):  # favorite taker price ~ f(|lead|); maker ~0.05-0.08 cheaper (not modeled here)
    return min(0.96,max(0.60,0.60+0.013*abs(lead)))
trades=[]
for st in range(int(LO//300)*300, NOW-300, 300):
    for cn in ("btc","eth"):
        o=PX[cn].get(st); p180=PX[cn].get(st+180); cl=PX[cn].get(st+300)
        if None in (o,p180,cl): continue
        lead=math.log(p180/o)*1e4; side=1 if lead>=0 else -1
        c2=[PX[cn].get(st-60*i) for i in range(31)]; c2=[x for x in c2 if x]
        if len(c2)<20: continue
        vol=statistics.pstdev([math.log(c2[i]/c2[i-1])*1e4 for i in range(1,len(c2))])
        if vol<=0: continue
        z=abs(lead)/vol
        if z<2.5: continue
        won=(side>0 and cl>=o) or (side<0 and cl<o)
        trades.append({"won":won,"z":z,"px":price_model(lead)})
print("一周 z>=2.5 窗口: %d, 胜率 %.0f%%\n"%(len(trades),sum(1 for t in trades if t["won"])/len(trades)*100))
def sim(sizer,lbl):
    pnls=[]; cum=0; peak=0; maxdd=0; worst=0
    for t in trades:
        sh=sizer(t["z"])
        p=sh*((1-t["px"]) if t["won"] else -t["px"])
        pnls.append(p); cum+=p; peak=max(peak,cum); maxdd=min(maxdd,cum-peak); worst=min(worst,p)
    tot=sum(pnls); avgsh=statistics.mean(sizer(t["z"]) for t in trades)
    print("  %-22s 总PnL$%+7.1f | 最大回撤$%6.1f | 最差单笔$%6.1f | 均仓%.1f股"%(lbl,tot,maxdd,worst,avgsh))
print("=== 三种下注方案 (同样的窗口/胜负, 只改仓位) ===")
sim(lambda z:5,"固定5股")
sim(lambda z: 5 if z<3 else 10,"z加重 2x(z>=3→10)")
sim(lambda z: 5 if z<3 else (10 if z<4 else 15),"z加重 3x(3→10,4+→15)")
sim(lambda z: min(15,round(5*z/2.5)),"z线性(5*z/2.5,封顶15)")
print("\n注: 价格是模型估的(taker-ish); maker实际更便宜→真PnL更好。重点看回撤/最差单笔的相对放大。")