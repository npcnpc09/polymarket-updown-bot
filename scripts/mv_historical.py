"""Historical backtest-evolution of the variants — INSTANT, on a week of real outcomes. We lack historical
PM ask prices, but variant differentiation is mostly about WHERE capital lands (value-weight on winners),
which needs only: binance lead PATH (signal, any history) + real outcomes (ce25 redeems). For each window,
simulate each variant's base/add/wobble decisions on the 1s lead path; outcome from real redeem. Rank by
CAPITAL-WEIGHTED win rate (shares-on-winners / total shares = does the averaging concentrate on winners) +
heavy-window win%. (Absolute EV/$ needs real prices -> live DRY; this nails the win-rate/selection half fast.)"""
import json,os,math,time,statistics
import httpx
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
c=httpx.Client(timeout=20,headers={"User-Agent":"Mozilla/5.0"})
OUT=["Up","Down"]; SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
OFF_BASE=(15,70); ADD_CHECKS=[90,150,210]
VARIANTS=[
 {"n":"A_base","lb":5,"bs":5,"as_":5,"la":8,"rt":3,"ma":3},
 {"n":"B_valweight","lb":5,"bs":2,"as_":10,"la":8,"rt":3,"ma":3},
 {"n":"C_tightbase","lb":8,"bs":5,"as_":5,"la":8,"rt":3,"ma":3},
 {"n":"D_looseRetrace","lb":5,"bs":5,"as_":5,"la":8,"rt":5,"ma":3},
 {"n":"E_tightRetrace","lb":5,"bs":5,"as_":5,"la":8,"rt":2,"ma":3},
 {"n":"F_moreAdds","lb":5,"bs":3,"as_":6,"la":8,"rt":3,"ma":5},
 {"n":"G_baseOnly","lb":5,"bs":5,"as_":0,"la":99,"rt":3,"ma":0},   # no adds = single-shot baseline
 {"n":"H_strongAdd","lb":5,"bs":3,"as_":8,"la":12,"rt":3,"ma":3},
 {"n":"I_valTight","lb":8,"bs":2,"as_":10,"la":10,"rt":3,"ma":3},
 {"n":"J_lateBase","lb":8,"bs":3,"as_":7,"la":10,"rt":4,"ma":4},
]
# real winners from ce25_full
RW={}
for l in open(os.path.join(ROOT,"data","ce25_full.jsonl"),encoding="utf-8"):
    r=json.loads(l); s=r.get("slug","")
    if "updown" not in s or "-5m-" not in s: continue
    w=RW.setdefault(s,{"buys":[],"ridx":None,"rsize":0.0})
    if r.get("type")=="TRADE" and r.get("side","").upper()=="BUY": w["buys"].append((r.get("outcome"),r.get("size") or 0))
    elif r.get("type")=="REDEEM":
        w["rsize"]+=r.get("size") or 0
        if r.get("outcomeIndex") is not None: w["ridx"]=r.get("outcomeIndex")
def winner(s):
    w=RW.get(s)
    if not w: return None
    if w["ridx"] in (0,1): return OUT[w["ridx"]]
    if w["rsize"]>0:
        up=sum(z for o,z in w["buys"] if o=="Up"); dn=sum(z for o,z in w["buys"] if o=="Down")
        return "Up" if abs(w["rsize"]-up)<abs(w["rsize"]-dn) else "Down"
    return None
wins=[]
for s in RW:
    parts=s.split("-"); coin=parts[0]
    if coin not in SYM: continue
    try: st=int(parts[-1])
    except: continue
    if winner(s): wins.append((coin,st,winner(s)))
wins.sort(key=lambda x:-x[1]); wins=wins[:400]   # most recent 400 (btc/eth) for speed
print("历史窗口(真实结算) %d 个, 拉binance 1秒lead路径...\n"%len(wins))
def leadpath(coin,st):
    try:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1s","startTime":st*1000,"endTime":(st+260)*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: return None
        op=float(k[0][1]); d={int(x[0]//1000)-st:float(x[4]) for x in k}
        def lat(off):
            ks=[o for o in d if o>=off]
            return math.log(d[min(ks)]/op)*1e4 if ks else None
        return lat
    except: return None
def sim(v,lat):
    side=None;lb=None;peak=None;fills=[];adds=set();wob=False
    # base
    for sec in range(OFF_BASE[0],OFF_BASE[1]+1,3):
        l=lat(sec)
        if l is None: continue
        if abs(l)>=v["lb"]: side="Up" if l>=0 else "Down"; lb=abs(l); peak=abs(l); fills.append(v["bs"]); break
    if side is None: return None
    # adds
    for ck in ADD_CHECKS:
        if v["ma"]<=0 or len(adds)>=v["ma"]: break
        l=lat(ck)
        if l is None: continue
        lt=l*(1 if side=="Up" else -1)
        if lt>peak: peak=lt
        if peak-lt>v["rt"]: wob=True; break
        if lt>=v["la"] and lt>=lb: adds.add(ck); fills.append(v["as_"])
    return side,sum(fills),len(fills)
res={v["n"]:{"n":0,"sh_win":0.0,"sh_tot":0.0,"wins":0,"heavy":0,"heavy_win":0} for v in VARIANTS}
done=0
for coin,st,win in wins:
    lat=leadpath(coin,st)
    if lat is None: continue
    done+=1
    for v in VARIANTS:
        r=sim(v,lat)
        if not r: continue
        side,sh,nf=r; won=(side==win)
        R=res[v["n"]]; R["n"]+=1; R["sh_tot"]+=sh; R["wins"]+=1 if won else 0
        if won: R["sh_win"]+=sh
        if nf>=3: R["heavy"]+=1; R["heavy_win"]+=1 if won else 0
print("成功重建 %d 窗\n"%done)
rows=[]
for v in VARIANTS:
    R=res[v["n"]]
    if R["n"]==0: continue
    rows.append({"v":v["n"],"n":R["n"],"win":R["wins"]/R["n"]*100,"cwwin":R["sh_win"]/R["sh_tot"]*100 if R["sh_tot"] else 0,"hn":R["heavy"],"hw":R["heavy_win"]/R["heavy"]*100 if R["heavy"] else None})
rows.sort(key=lambda x:-x["cwwin"])
print("=== 历史回测排名 (按\033[1m资金加权胜率\033[0m=钱堆在赢家的比例) ===")
print("%-15s %4s %5s %8s %s"%("变体","n","胜%","资金权胜%","重仓胜%/n"))
for i,r in enumerate(rows):
    hw="%2.0f%%/%d"%(r["hw"],r["hn"]) if r["hw"] is not None else "—/0"
    print("%s%-14s %4d %4.0f%% %7.0f%%  %s"%("★" if i==0 else " ",r["v"],r["n"],r["win"],r["cwwin"],hw))
print("\n资金权胜% = 落在赢家上的股数/总股数. 越高=averaging越把钱堆在赢家上(value-weight有效).")
print("G_baseOnly = 不加码的单发基准, 对比它看'加码'到底加不加分.")
print("注: 胜负=真实赎回结算(可信). 缺历史价->绝对EV要live DRY补; 这里评的是\033[1m选择/胜率\033[0m那半.")
