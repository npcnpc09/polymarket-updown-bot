"""REAL sizing backtest: use the ENGINE'S OWN recorded entries (real ask B, real settlement won) — the
84%-win ground truth, NOT a reconstruction. Reconstruct z=|lead|/vol, filter z>=2.5, order by time, and
simulate fixed vs value-weighted sizing. Report total PnL, MAX DRAWDOWN, WORST single loss, WORST losing
cluster (the real tail risk of betting heavy without eebde's diversification)."""
import json,math,httpx,statistics,datetime
ROWS=[]
for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if "won" in r and isinstance(r.get("B"),(int,float)) and r.get("coin")in("btc","eth") and "-5m-" in r.get("slug","") and isinstance(r.get("lead"),(int,float)):
        ROWS.append(r)
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}; sts=[int(r["slug"].split("-")[-1]) for r in ROWS]
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
def fetch(sym,lo,hi):
    out={};cur=lo
    while cur<hi:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=float(x[1])
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
BN={cn:fetch(SYM[cn],min(sts)-2000,max(sts)+60) for cn in SYM}
T=[]
for r in ROWS:
    cn=r["coin"]; st=int(r["slug"].split("-")[-1])
    cl=[BN[cn].get(st-60*i) for i in range(31)]; cl=[x for x in cl if x]
    if len(cl)<20: continue
    vol=statistics.pstdev([math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))])
    if vol<=0: continue
    z=abs(r["lead"])/vol
    if z<2.5: continue
    T.append({"st":st,"won":r["won"],"B":r["B"],"z":z})
T.sort(key=lambda x:x["st"])
print("真实 z>=2.5 成交: %d (跨%.1f天), 真实胜率 %.0f%%, 均价B %.3f\n"%(
    len(T),(T[-1]["st"]-T[0]["st"])/86400,sum(1 for t in T if t["won"])/len(T)*100,statistics.mean(t["B"] for t in T)))
def sim(sizer,lbl):
    cum=0;peak=0;maxdd=0;worst=0; clus=0; worstclus=0
    for t in T:
        sh=sizer(t["z"]); p=sh*((1-t["B"]) if t["won"] else -t["B"])
        cum+=p; peak=max(peak,cum); maxdd=min(maxdd,cum-peak); worst=min(worst,p)
        clus = (clus+p) if p<0 else 0; worstclus=min(worstclus,clus)  # consecutive-loss cluster
    print("  %-20s 总PnL$%+6.1f | 最大回撤$%6.1f | 最差单笔$%5.1f | 最差连亏簇$%6.1f | 均仓%.1f"%(
        lbl,cum,maxdd,worst,worstclus,statistics.mean(sizer(t["z"]) for t in T)))
print("=== 真实数据下的下注方案对比 ===")
sim(lambda z:5,"固定5股")
sim(lambda z: 5 if z<3 else 10,"z>=3→10 (2x)")
sim(lambda z: 5 if z<3 else (10 if z<4 else 15),"3→10,4+→15 (3x)")
print("\n注: B是真实ask(taker); maker实际更便宜→真PnL更好, 但回撤/尾部的相对放大是真实的。")
print("对比: 这是真实84%胜率, 不是之前虚高的97%。")