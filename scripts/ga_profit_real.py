"""GA on REAL prices x REAL settlement — the clean version. ga_profit.py exposed that binance-reconstructed
outcomes are SYSTEMATICALLY biased on cheap longshots, and train/test split does NOT catch it (same bias both
sides). Fix: use the 600-window cache's REAL redeem-based winners. Pull ALL-trader fills for those windows,
label won/lost by the REAL winner, lead from the cached 1s path. Same GA (genome = lead/price/offset ranges,
fitness = train ROI, arbiter = TEST ROI). Now a +ROI rule that survives TEST is REAL mispricing, not artifact.
If none survives -> selection edge is genuinely priced-in to takers (the honest wall). Caches fills once."""
import httpx,math,statistics,time,json,os,sys,random
from collections import defaultdict
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FC=os.path.join(ROOT,"data","alltrader_fills_real.json")
def build():
    cache=json.load(open(os.path.join(ROOT,"data","lead_paths.json")))  # "coin|st" -> {win, lead:{off:bps}}
    # slug -> conditionId from ce25_full
    cid={}
    for l in open(os.path.join(ROOT,"data","ce25_full.jsonl"),encoding="utf-8"):
        r=json.loads(l); s=r.get("slug","")
        if s and r.get("conditionId") and s not in cid: cid[s]=r["conditionId"]
    c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
    keys=list(cache.items()); print("拉 %d 窗的全市场成交 (真实赎回赢家)..."%len(keys))
    fills=[]; ok=0
    for i,(key,v) in enumerate(keys):
        coin,st=key.split("|"); st=int(st); slug=f"{coin}-updown-5m-{st}"
        cd=cid.get(slug)
        if not cd: continue
        win=v["win"]; path={int(o):b for o,b in v["lead"].items()}
        try: trs=c.get("https://data-api.polymarket.com/trades",params={"market":cd,"limit":1000}).json()
        except: continue
        if not isinstance(trs,list): continue
        ok+=1
        for t in trs:
            if (t.get("side") or "").upper()!="BUY": continue
            p=t.get("price") or 0; oc=t.get("outcome"); sz=t.get("size") or 0; ts=t.get("timestamp")
            if not (0<p<1) or oc not in ("Up","Down") or sz<=0 or not ts: continue
            off=int(ts-st)
            if off<0 or off>300: continue
            ks=[o for o in path if o>=off]
            if not ks: continue
            lead=path[min(ks)]*(1 if oc=="Up" else -1)
            fills.append({"slug":slug,"coin":coin,"price":round(p,3),"won":(oc==win),"size":sz,"lead":round(lead,1),"off":off})
        if i%80==0 and i: print("  ...%d窗 %d笔"%(i,len(fills)))
    json.dump(fills,open(FC,"w")); print("缓存 %d 笔, %d窗有成交 -> %s\n"%(len(fills),ok,FC)); return fills
fills=json.load(open(FC)) if os.path.exists(FC) else build()
slugs=sorted(set(f["slug"] for f in fills)); tr=set(slugs[::2]); te=set(slugs[1::2])
TR=[f for f in fills if f["slug"] in tr]; TE=[f for f in fills if f["slug"] in te]
print("总 %d 笔 | train %d窗/%d笔  test %d窗/%d笔 (真实结算, 无伪影)\n"%(len(fills),len(tr),len(TR),len(te),len(TE)))
def roi(rs):
    sp=sum(f["size"]*f["price"] for f in rs)
    if not sp: return 0,0
    pf=sum((f["size"]*(1-f["price"]) if f["won"] else -f["size"]*f["price"]) for f in rs); return pf/sp*100,len(rs)
def sel(rs,g):
    ll,lh,pl,ph,ol,oh=g; return [f for f in rs if ll<=f["lead"]<lh and pl<=f["price"]<ph and ol<=f["off"]<oh]
def fitness(g):
    r,n=roi(sel(TR,g)); return r if n>=200 else -1e9
def rnd():
    ll=random.uniform(-10,25); lh=ll+random.uniform(3,50); pl=random.uniform(0.05,0.85); ph=pl+random.uniform(0.05,0.6)
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
random.seed(7); POP=100; GEN=40; pop=[rnd() for _ in range(POP)]
for gen in range(GEN):
    scored=sorted(((fitness(g),g) for g in pop),key=lambda x:-x[0]); elite=[g for _,g in scored[:20]]; pop=elite[:]
    while len(pop)<POP:
        if random.random()<0.5: a,b=random.sample(elite,2); pop.append([random.choice(p) for p in zip(a,b)])
        else: pop.append(mut(random.choice(elite)))
    pop+=[rnd() for _ in range(10)]
seen=set(); rows=[]
for g in sorted(pop,key=lambda g:-fitness(g)):
    kg=tuple(g)
    if kg in seen: continue
    seen.add(kg)
    rtr,ntr=roi(sel(TR,g)); rte,nte=roi(sel(TE,g))
    if ntr<200 or nte<80: continue
    sf=sel(fills,g); cheap=sum(1 for f in sf if f["price"]<0.3)/max(1,len(sf))*100
    rows.append((g,rtr,ntr,rte,nte,cheap))
    if len(rows)>=14: break
print("=== GA on 真价×真结算 (train挑选 -> TEST裁决) ===")
print("%-26s %8s %8s %6s %6s %s"%("规则[leadLo,Hi,pxLo,Hi,offLo,Hi]","trainROI","testROI","trN","teN","便宜<0.3"))
for g,rtr,ntr,rte,nte,cheap in rows:
    ok="✅test也正" if rte>1.5 else ("✗过拟合(test塌)" if rtr-rte>4 else "·")
    print("%-26s %+7.1f%% %+7.1f%% %6d %6d %4.0f%% %s"%(str(g),rtr,rte,ntr,nte,cheap,ok))
allr,_=roi(fills); print("\n全样本基准ROI %+.1f%% (=盲买所有真实成交). 真结算下若没有test明显>0的规则 => 选择edge对taker确实priced-in."%allr)
