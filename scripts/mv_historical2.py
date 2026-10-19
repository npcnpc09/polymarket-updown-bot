"""Gen-2 historical evolution — ~22 creative variants with NEW alphas (all from binance lead path, no prices):
z-score(vol-normalized) gates, PYRAMIDING adds (scaling sizes), ACCELERATION-gated adds, earlier base, finer
add checkpoints, stricter strengthening. Ranked by capital-weighted win rate (shares-on-winners/total) on
400 real-settled windows + HALF-SPLIT cross-validation (rank stable across both halves = not luck)."""
import json,os,math,statistics
import httpx
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
c=httpx.Client(timeout=20,headers={"User-Agent":"Mozilla/5.0"})
OUT=["Up","Down"]; SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
# variant spec: gate type/threshold, base offset window, add checkpoints, add gate, retrace, sizes(pyramid),
#   strengthen_min (lead must exceed base by this to add), accel_min (lead accel over last 30s, optional)
def V(n,**k):
    d=dict(gate="lead",gt=5,offlo=15,offhi=70,checks=[90,150,210],agate="lead",agt=8,rt=3,
           sizes=[5,5,5,5,5,5],strq=0,accel=None); d.update(k); d["n"]=n; return d
VARIANTS=[
 V("A_base"), V("G_baseOnly",sizes=[5],checks=[]),
 V("I_valTight",gt=8,sizes=[2,10,10,10],agt=10),                       # gen1 winner
 V("B_valweight",sizes=[2,10,10]),
 # --- pyramiding (scaling adds) ---
 V("P1_pyramid",gt=8,sizes=[2,5,10,15],agt=9),
 V("P2_pyramidX",gt=8,sizes=[1,4,9,16,20],agt=9,checks=[60,100,150,210]),
 V("P3_heavyTail",gt=8,sizes=[2,6,18],agt=10),
 # --- z-score (vol-normalized, regime-proof) ---
 V("Z1_z25",gate="z",gt=2.5,agate="z",agt=3.0,sizes=[2,10,10]),
 V("Z2_z30",gate="z",gt=3.0,agate="z",agt=3.5,sizes=[2,10,12]),
 V("Z3_zpyr",gate="z",gt=2.5,agate="z",agt=3.0,sizes=[1,5,10,15]),
 # --- acceleration-gated adds (only add if lead is still accelerating) ---
 V("AC1_accel",gt=8,sizes=[2,10,12],agt=8,accel=2.0),
 V("AC2_accelTight",gt=8,sizes=[2,10,14],agt=10,accel=3.0),
 # --- earlier base (cheaper) ---
 V("EB1_early",gt=4,offlo=5,offhi=40,sizes=[3,8,10],agt=8),
 V("EB2_earlyTight",gt=5,offlo=5,offhi=30,sizes=[2,10,12],agt=10),
 # --- finer/more add checkpoints ---
 V("FC1_fine",gt=8,checks=[60,90,120,150,180,210],sizes=[2,4,6,8,10,12],agt=9,strq=2),
 V("FC2_dense",gt=6,checks=[45,75,105,135,165,195,225],sizes=[2,3,5,7,9,11,13],agt=8),
 # --- stricter strengthening (lead must EXCEED base by strq to add) ---
 V("ST1_strict",gt=8,sizes=[2,10,14],agt=10,strq=3),
 V("ST2_strictX",gt=8,sizes=[1,8,16],agt=12,strq=5),
 # --- combos (天马行空) ---
 V("CB1_zPyrAcc",gate="z",gt=2.5,agate="z",agt=3.0,sizes=[1,5,12,18],accel=2.0,checks=[60,110,160,210]),
 V("CB2_tightAll",gt=10,offlo=10,offhi=50,sizes=[1,8,16],agt=12,rt=2,strq=4),
 V("CB3_looseRideHard",gt=6,sizes=[2,6,12,20],agt=8,rt=6,checks=[60,110,160,210],strq=2),
]
# real winners
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
wins.sort(key=lambda x:-x[1]); wins=wins[:400]
print("历史窗口 %d, 拉1秒lead路径...\n"%len(wins))
def fetch(coin,st):
    try:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1s","startTime":st*1000,"endTime":(st+260)*1000,"limit":1000}).json()
        if not isinstance(k,list) or len(k)<60: return None
        op=float(k[0][1]); pr={int(x[0]//1000)-st:float(x[4]) for x in k}
        return op,pr
    except: return None
def lead(op,pr,off):
    ks=[o for o in pr if o>=off]
    return math.log(pr[min(ks)]/op)*1e4 if ks else None
def vol_at(op,pr,off):  # realized 1s lead vol over last ~40s (choppiness normalizer for z)
    seg=[pr[o] for o in sorted(pr) if off-40<=o<=off]
    if len(seg)<5: return 1.0
    r=[math.log(seg[i]/seg[i-1])*1e4 for i in range(1,len(seg))]
    m=sum(r)/len(r); v=(sum((x-m)**2 for x in r)/len(r))**0.5
    return max(v,0.3)
def metric(v,op,pr,off,side=None):
    l=lead(op,pr,off)
    if l is None: return None,None
    lt=l*(1 if side=="Up" else -1) if side else abs(l)
    if v["gate"]=="z" or v["agate"]=="z":
        z=lt/vol_at(op,pr,off)
        return l,z
    return l,lt
def sim(v,op,pr):
    side=lb=peak=None; fills=[]; wob=False
    for off in range(v["offlo"],v["offhi"]+1,3):
        l,m=metric(v,op,pr,off)
        if m is None: continue
        thr=v["gt"]
        if m>=thr: side="Up" if l>=0 else "Down"; lb=abs(l); peak=abs(l); fills.append(v["sizes"][0]); break
    if side is None: return None
    ai=1
    for off in v["checks"]:
        if ai>=len(v["sizes"]): break
        l,m=metric(v,op,pr,off,side)  # m = add-metric toward side (lead or z)
        if l is None: continue
        lt=l*(1 if side=="Up" else -1)
        if lt>peak: peak=lt
        if peak-lt>v["rt"]: wob=True; break
        # strengthen: lead must exceed base by strq
        if lt < lb+v["strq"]: continue
        # add gate
        am = (lt/vol_at(op,pr,off)) if v["agate"]=="z" else lt
        if am < v["agt"]: continue
        # acceleration: lead grew over last 30s
        if v["accel"] is not None:
            lp=lead(op,pr,off-30)
            if lp is None or (lt-(lp*(1 if side=="Up" else -1)))<v["accel"]: continue
        fills.append(v["sizes"][ai]); ai+=1
    return side,sum(fills),len(fills)
half=len(wins)//2
def run(subset):
    res={v["n"]:[0.0,0.0,0,0,0,0] for v in VARIANTS}  # sh_win, sh_tot, n, wins, heavy, heavy_win
    for coin,st,win in subset:
        fp=PATHS.get((coin,st))
        if not fp: continue
        op,pr=fp
        for v in VARIANTS:
            r=sim(v,op,pr)
            if not r: continue
            sd,sh,nf=r; won=(sd==win); R=res[v["n"]]
            R[1]+=sh; R[2]+=1; R[3]+=1 if won else 0
            if won: R[0]+=sh
            if nf>=3: R[4]+=1; R[5]+=1 if won else 0
    return res
PATHS={}
for coin,st,win in wins:
    f=fetch(coin,st)
    if f: PATHS[(coin,st)]=f
print("成功重建 %d 窗\n"%len(PATHS))
full=run(wins); h1=run(wins[:half]); h2=run(wins[half:])
def cww(R): return R[0]/R[1]*100 if R[1] else 0
rows=[{"v":v["n"],"n":full[v["n"]][2],"win":full[v["n"]][3]/full[v["n"]][2]*100 if full[v["n"]][2] else 0,
       "cww":cww(full[v["n"]]),"h1":cww(h1[v["n"]]),"h2":cww(h2[v["n"]]),
       "hw":full[v["n"]][5]/full[v["n"]][4]*100 if full[v["n"]][4] else None,"hn":full[v["n"]][4]} for v in VARIANTS if full[v["n"]][2]>0]
rows.sort(key=lambda x:-x["cww"])
print("=== Gen-2 历史排名 (资金加权胜率, 含半分交叉验证) ===")
print("%-15s %4s %4s %7s %s %s"%("变体","n","胜%","资金权胜%","[半1/半2]","重仓胜%/n"))
for i,r in enumerate(rows):
    hw="%2.0f%%/%d"%(r["hw"],r["hn"]) if r["hw"] is not None else "—"
    stable="稳" if abs(r["h1"]-r["h2"])<6 else "波动"
    print("%s%-14s %4d %3.0f%% %6.0f%%  [%2.0f/%2.0f %s] %s"%("★" if i==0 else " ",r["v"],r["n"],r["win"],r["cww"],r["h1"],r["h2"],stable,hw))
print("\n资金权胜%=钱落在赢家比例; [半1/半2]=前后半各自的值, 接近=稳(非运气); 重仓胜%=2+加仓窗.")
print("缺历史价 -> 绝对EV要live DRY; 这里评选择/胜率半 (秒出, 400真实结算窗).")
