"""Current market regime: strong TREND or CHOP? Pull recent BTC/ETH klines. Report (a) net trend over
15/30/60m, (b) realized 1m vol, (c) chop_ratio = intra-30m range / |net 30m move| (high=choppy), and crucially
(d) the last ~8 completed 5m windows: did the within-window lead PERSIST to settle (trend) or REVERSE (chop)?
That last one is what actually hits our strategy."""
import httpx,math,time
c=httpx.Client(timeout=20,headers={"User-Agent":"Mozilla/5.0"})
def kl(sym,interval,limit,start=None,end=None):
    p={"symbol":sym,"interval":interval,"limit":limit}
    if start: p["startTime"]=start*1000
    if end: p["endTime"]=end*1000
    return c.get("https://api.binance.com/api/v3/klines",params=p).json()
now=int(time.time())
for coin,sym in (("btc","BTCUSDT"),("eth","ETHUSDT")):
    k=kl(sym,"1m",90); cl=[float(x[4]) for x in k]
    def ret(mins): return math.log(cl[-1]/cl[-mins])*1e4
    rets=[math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))]
    m=sum(rets[-30:])/30; vol=(sum((x-m)**2 for x in rets[-30:])/30)**0.5
    hi=max(cl[-30:]); lo=min(cl[-30:]); rng=math.log(hi/lo)*1e4; net30=abs(ret(30))
    chop=rng/max(net30,1)
    print("%s: 15m %+.0f  30m %+.0f  60m %+.0f bps | 30m振幅 %.0f / 净 %.0f = chop_ratio \033[1m%.1f\033[0m | vol %.1f"%(
        coin.upper(),ret(15),ret(30),ret(60),rng,net30,chop,vol))
# last 8 completed 5m windows: lead persist vs reverse
print("\n=== 最近8个完成的5m窗 (lead是否持续到结算) ===")
print("%-5s %-12s %8s %8s %7s %s"%("币","窗start","峰lead","终lead","结果","判定"))
persist=0; rev=0; tot=0
for coin,sym in (("btc","BTCUSDT"),("eth","ETHUSDT")):
    base=(now//300)*300
    for i in range(1,5):
        st=base-i*300
        kk=kl(sym,"1s",320,start=st,end=st+300)
        if not isinstance(kk,list) or len(kk)<60: continue
        op=float(kk[0][1]); leads=[math.log(float(x[4])/op)*1e4 for x in kk]
        final=leads[-1]; sgn=1 if final>=0 else -1
        peakopp=max((l*-( 1 if final>=0 else -1)) for l in leads)  # peak toward the LOSING side
        peaktoward=max(l*sgn for l in leads)
        # reversal = at some point lead went >=8 toward the side that ultimately LOST
        opppeak=max(abs(l) for l in leads if (l>=0)!=(final>=0)) if any((l>=0)!=(final>=0) for l in leads) else 0
        tag="反转" if opppeak>=8 else ("持续" if abs(final)>=5 else "平")
        if tag=="反转": rev+=1
        elif tag=="持续": persist+=1
        tot+=1
        print("%-5s %-12d %+7.0f %+7.0f %6s %s"%(coin,st,peaktoward,final,"Up" if final>=0 else "Down",tag))
print("\n最近%d窗: 持续 %d / 反转 %d / 平 %d"%(tot,persist,rev,tot-persist-rev))
print("反转多 => 现在是CHOP(我们lead策略挨打); 持续多 => TREND(lead策略顺风).")
