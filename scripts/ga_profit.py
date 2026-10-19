"""Genetic algorithm over SELECTION RULES, fitness = REAL ROI on ALL-trader real fills (real prices paid +
binance outcome). NOT a calibrated price model (that's EV=0 by construction) — real prices are the only place
mispricing can hide. Genome = (lead_lo,lead_hi, price_lo,price_hi, off_lo,off_hi): the rule 'take every real
BUY whose lead-toward-side, price, and entry-offset fall in these ranges'. Fitness = ROI on TRAIN windows;
the ONLY valid winner is one that's ALSO +ROI on held-out TEST windows (split by window -> no leakage).
Cheap-band (<0.3) reliance flagged = binance-reconstruction artifact. Caches fills once -> data/alltrader_fills.json"""
import httpx,math,statistics,time,json,os,sys,random
from collections import defaultdict
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FC=os.path.join(ROOT,"data","alltrader_fills.json")
CE="0xcE25E214D5cfE4f459cf67F08DF581885AAE7Fdc"
def build():
    c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"}); A=[]
    for off in range(0,5000,500):
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
    wins=dict(list(wins.items())[:220]); print("拉 %d 窗全市场成交(一次性缓存)..."%len(wins))
    need=set(v[1] for v in wins.values());KL={}
    for coin in need:
        sts=[v[3] for v in wins.values() if v[1]==coin]; out={};cur=min(sts)-180;hi=max(v[3]+DUR[v[2]] for v in wins.values() if v[1]==coin)+300
        while cur<hi:
            k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
            if not isinstance(k,list) or not k: break
            for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[4]))
            cur=int(k[-1][0]//1000)+60
            if len(k)<1000: break
        KL[coin]=out
    def pxat(coin,t):
        d=KL[coin];lo=(t//60)*60;aa=d.get(lo);bb=d.get(lo+60)
        return aa[0]+((bb[0]-aa[0])*((t-lo)/60.0) if bb else 0) if aa else None
    fills=[]
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
            if not (0<p<1) or oc not in ("Up","Down") or sz<=0 or not ts or ts<st or ts>st+DUR[dur]: continue
            bp=pxat(coin,int(ts))
            if not bp: continue
            lead=math.log(bp/op)*1e4*(1 if oc=="Up" else -1)
            fills.append({"slug":slug,"coin":coin,"price":round(p,3),"won":(oc==win),"size":sz,"lead":round(lead,1),"off":int(ts-st)})
    json.dump(fills,open(FC,"w")); print("缓存 %d 笔 -> %s\n"%(len(fills),FC)); return fills
fills=json.load(open(FC)) if os.path.exists(FC) else build()
# train/test split by WINDOW (deterministic, no leakage)
slugs=sorted(set(f["slug"] for f in fills)); tr=set(slugs[::2]); te=set(slugs[1::2])
TR=[f for f in fills if f["slug"] in tr]; TE=[f for f in fills if f["slug"] in te]
print("总 %d 笔 | train %d窗/%d笔  test %d窗/%d笔\n"%(len(fills),len(tr),len(TR),len(te),len(TE)))
def roi(rs):
    sp=sum(f["size"]*f["price"] for f in rs)
    if not sp: return 0,0
    pf=sum((f["size"]*(1-f["price"]) if f["won"] else -f["size"]*f["price"]) for f in rs)
    return pf/sp*100, len(rs)
def sel(rs,g):
    ll,lh,pl,ph,ol,oh=g
    return [f for f in rs if ll<=f["lead"]<lh and pl<=f["price"]<ph and ol<=f["off"]<oh]
def fitness(g):
    r,n=roi(sel(TR,g))
    return r if n>=200 else -1e9
def rnd():
    ll=random.uniform(-10,25); lh=ll+random.uniform(3,50)
    pl=random.uniform(0.05,0.85); ph=pl+random.uniform(0.05,0.6)
    ol=random.choice([0,0,0,30,60]); oh=ol+random.choice([60,120,180,300])
    return [round(ll,1),round(lh,1),round(pl,2),round(min(ph,1.0),2),ol,oh]
def mut(g):
    g=g[:]; i=random.randrange(6)
    if i==0: g[0]=round(g[0]+random.uniform(-5,5),1)
    elif i==1: g[1]=round(max(g[0]+2,g[1]+random.uniform(-8,8)),1)
    elif i==2: g[2]=round(min(max(0.02,g[2]+random.uniform(-0.1,0.1)),0.95),2)
    elif i==3: g[3]=round(min(max(g[2]+0.03,g[3]+random.uniform(-0.1,0.1)),1.0),2)
    elif i==4: g[4]=max(0,g[4]+random.choice([-30,30]))
    else: g[5]=max(g[4]+60,g[5]+random.choice([-60,60]))
    return g
random.seed(7)
POP=100; GEN=40
pop=[rnd() for _ in range(POP)]
for gen in range(GEN):
    scored=sorted(((fitness(g),g) for g in pop),key=lambda x:-x[0])
    elite=[g for _,g in scored[:20]]
    pop=elite[:]
    while len(pop)<POP:
        if random.random()<0.5:
            a,b=random.sample(elite,2); pop.append([random.choice(p) for p in zip(a,b)])
        else: pop.append(mut(random.choice(elite)))
    pop+= [rnd() for _ in range(10)]  # fresh blood
# final ranking: train + TEST (the real arbiter)
seen=set(); rows=[]
for g in sorted(pop,key=lambda g:-fitness(g)):
    kg=tuple(g)
    if kg in seen: continue
    seen.add(kg)
    rtr,ntr=roi(sel(TR,g)); rte,nte=roi(sel(TE,g))
    if ntr<200 or nte<80: continue
    selfills=sel(fills,g); cheap=sum(1 for f in selfills if f["price"]<0.3)/max(1,len(selfills))*100
    rows.append((g,rtr,ntr,rte,nte,cheap))
    if len(rows)>=14: break
print("=== GA 最优规则 (train挑选 -> TEST裁决) ===")
print("%-26s %7s %7s %6s %6s %s"%("规则[leadLo,Hi,pxLo,Hi,offLo,Hi]","trainROI","testROI","trN","teN","便宜<0.3占比"))
for g,rtr,ntr,rte,nte,cheap in rows:
    ok="✅真" if rte>1.5 else ("✗过拟合" if rtr>3 else "·")
    art=" ⚠伪影" if cheap>40 else ""
    print("%-26s %+7.1f%% %+7.1f%% %6d %6d %4.0f%%%s %s"%(str(g),rtr,rte,ntr,nte,cheap,art,ok))
print("\n判读: 只信 \033[1mtestROI 也明显>0\033[0m 的(train高test低=过拟合, 100变体撞出来的假阳).")
print("便宜<0.3占比高=靠longshot伪影, 打假. 真价上若没有test也正的规则 => 选择edge确实priced-in, taker拿不到.")
