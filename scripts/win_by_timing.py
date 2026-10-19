"""Win-rate vs ENTRY TIMING, from 1s binance lead paths. For each 5m window, if |lead|>=8 at offset T
(same-side), entering there wins? Bucket by T. Tests the user's hypothesis 'earlier entry = higher win'.
Also reports avg |lead| at each T (proxy for how expensive = price rises with lead). No PM price needed for
the win-rate question."""
import httpx,math,time,statistics
c=httpx.Client(timeout=20,headers={"User-Agent":"Mozilla/5.0"})
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}; TRIG=8.0
OFFSETS=[20,40,60,90,120,150,180,240]
now=int(time.time()); windows=[]
for coin,sym in COINS.items():
    base=(now//300)*300
    for k in range(1,55):
        st=base-k*300
        if st+300<now-20: windows.append((coin,sym,st))
def kl1s(sym,st):
    out={}
    r=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1s","startTime":st*1000,"endTime":(st+300)*1000,"limit":1000}).json()
    if isinstance(r,list):
        for x in r: out[int(x[0]//1000)-st]=float(x[4])
    return out
rows=[]
for coin,sym,st in windows:
    px=kl1s(sym,st)
    if len(px)<200: continue
    op=px.get(0) or px[min(px)]; cl=px.get(299) or px.get(max(k for k in px if k<=300))
    if not op or not cl: continue
    winner="Up" if cl>=op else "Down"
    lead={t:math.log(p/op)*1e4 for t,p in px.items()}
    rec={"winner":winner}
    for T in OFFSETS:
        nb=min((k for k in lead if k>=T),default=None)
        if nb is not None and abs(lead[nb])>=TRIG:
            side="Up" if lead[nb]>=0 else "Down"
            rec[T]=(side==winner,abs(lead[nb]))
        else: rec[T]=None
    rows.append(rec)
print("窗口 %d\n"%len(rows))
print("=== 在固定时点T入场(lead>=8同向): 胜率 vs 时点 ===")
print("  %-6s %5s %6s %7s"%("时点","笔","胜率","均|lead|(越大=越贵)"))
for T in OFFSETS:
    g=[r[T] for r in rows if r[T] is not None]
    if g: print("  %4ds %5d  %4.0f%%  %6.1f"%(T,len(g),sum(1 for w,_ in g if w)/len(g)*100,statistics.mean(l for _,l in g)))
print("\n=== 关键对比: 早(<=60s) vs 晚(>=150s) ===")
early=[r[40] for r in rows if r[40] is not None]; late=[r[150] for r in rows if r[150] is not None]
if early and late:
    print("  早入(40s):  胜%.0f%% 均lead%.1f"%(sum(1 for w,_ in early if w)/len(early)*100,statistics.mean(l for _,l in early)))
    print("  晚入(150s): 胜%.0f%% 均lead%.1f"%(sum(1 for w,_ in late if w)/len(late)*100,statistics.mean(l for _,l in late)))
print("\n注: 胜率↑随时点 = 晚入更准但lead更大(价更贵); 这就是'便宜vs准'的tradeoff. 市场calibrated下两头≈breakeven.")
