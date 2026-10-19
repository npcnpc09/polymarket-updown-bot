"""Optimize for PROFIT (EV), not win rate. Each fill is priced via a REAL-DATA-grounded price(lead) model
(calibrated from real_taker_backtest: lead->avg fill price). EV per fill = shares*( (1-price) if win else
-price ). Re-rank variants by total EV across the cached windows + 3-fold CV. Reveals that win-rate-optimal
(heavy late-adds at 0.90) may NOT be profit-optimal (cheap base at 0.65 makes more $/win). Explore base-heavy
vs add-heavy sizing. (price model = proxy; live DRY confirms absolute EV — but RELATIVE profit ranking is the
signal.)"""
import json,os,math,statistics
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE=os.path.join(ROOT,"data","lead_paths.json")
cache=json.load(open(CACHE)); WINS=[(k,v["win"],v["lead"]) for k,v in cache.items()]
print("缓存窗口 %d\n"%len(WINS))
# real-data price(lead toward side) — calibrated from real_taker_backtest avg fill prices
PTS=[(0,0.52),(2,0.57),(5,0.72),(8,0.79),(11,0.867),(15,0.89),(20,0.913),(30,0.94),(50,0.95)]
def price(lead):
    lead=abs(lead)
    if lead<=PTS[0][0]: return PTS[0][1]
    for i in range(1,len(PTS)):
        if lead<=PTS[i][0]:
            (x0,y0),(x1,y1)=PTS[i-1],PTS[i]; return y0+(y1-y0)*(lead-x0)/(x1-x0)
    return PTS[-1][1]
def V(n,gt=8,offlo=15,offhi=70,checks=(90,150,210),agt=12,rt=3,sizes=(1,8,16),strq=3,cap=0.95):
    return dict(n=n,gt=gt,offlo=offlo,offhi=offhi,checks=list(checks),agt=agt,rt=rt,sizes=list(sizes),strq=strq,cap=cap)
def lead(path,off):
    for o in range(off,off+8):
        if str(o) in path: return path[str(o)]
    return None
def sim(v,path):
    """return (side, fills=[(lead,shares)])"""
    side=lb=peak=None; fills=[]
    for off in range(v["offlo"],v["offhi"]+1,3):
        l=lead(path,off)
        if l is None: continue
        if abs(l)>=v["gt"] and price(l)<v["cap"]:
            side="Up" if l>=0 else "Down"; lb=abs(l); peak=abs(l); fills.append((abs(l),v["sizes"][0])); break
    if side is None: return None
    ai=1
    for off in v["checks"]:
        if ai>=len(v["sizes"]): break
        l=lead(path,off)
        if l is None: continue
        lt=l*(1 if side=="Up" else -1)
        if lt>peak: peak=lt
        if peak-lt>v["rt"]: break
        if lt<lb+v["strq"] or lt<v["agt"] or price(lt)>=v["cap"]: continue
        fills.append((lt,v["sizes"][ai])); ai+=1
    return side,fills
# --- variants: span base-heavy(cheap) <-> add-heavy(expensive), price caps ---
VARIANTS=[
 V("winRateOpt",sizes=(1,10,25)),          # gen3 win-rate winner (heavy expensive adds)
 V("baseOnly",sizes=(5,),checks=(),agt=99),
 V("balanced",gt=5,sizes=(5,5,5),agt=8,strq=0),
 # base-heavy (load cheap base, light adds)
 V("baseHeavy1",gt=5,sizes=(15,4,1),agt=8,strq=2),
 V("baseHeavy2",gt=5,sizes=(20,3,1),agt=8,strq=2),
 V("baseHeavy3",gt=5,sizes=(10,5,3),agt=8,strq=2),
 V("baseHeavyTight",gt=8,sizes=(15,5,2),agt=10,strq=3),
 # cheap-only caps (refuse expensive)
 V("cap80",gt=5,sizes=(8,6,4),agt=8,strq=2,cap=0.80),
 V("cap85",gt=5,sizes=(8,6,4),agt=8,strq=2,cap=0.85),
 V("cap75base",gt=5,sizes=(10,5,2),agt=8,strq=2,cap=0.75),
 # early cheap base
 V("earlyCheap",gt=4,offlo=5,offhi=40,sizes=(12,5,2),agt=8,strq=2),
 V("earlyCheapCap",gt=4,offlo=5,offhi=40,sizes=(12,5,2),agt=8,strq=2,cap=0.82),
 # balanced pyramids
 V("midPyr",gt=8,sizes=(5,8,10),agt=10,strq=3),
 V("flatAvg",gt=6,sizes=(6,6,6),agt=8,strq=2),
 # add-heavy but cap the expensive tail
 V("addHeavyCap",gt=8,sizes=(2,8,14),agt=10,strq=3,cap=0.88),
 V("winOptCap88",sizes=(1,10,25),cap=0.88),
 V("winOptCap85",sizes=(1,10,25),cap=0.85),
]
folds=[WINS[i::3] for i in range(3)]
def run(subset):
    res={v["n"]:[0.0,0.0,0,0] for v in VARIANTS}  # ev, cost(=sum price*sh), n, wins
    for k,win,path in subset:
        for v in VARIANTS:
            r=sim(v,path)
            if not r: continue
            side,fills=r; won=(side==win); R=res[v["n"]]; R[2]+=1; R[3]+=1 if won else 0
            for ld,sh in fills:
                p=price(ld); R[1]+=p*sh
                R[0]+= sh*((1-p) if won else -p)
    return res
full=run(WINS); F=[run(f) for f in folds]
def roi(R): return R[0]/R[1]*100 if R[1] else 0
rows=[]
for v in VARIANTS:
    R=full[v["n"]]
    if R[2]==0: continue
    fr=[roi(F[i][v["n"]]) for i in range(3)]
    rows.append({"v":v["n"],"n":R[2],"win":R[3]/R[2]*100,"roi":roi(R),"ev":R[0],"avgsh":R[1]/R[2],"folds":fr,"spread":max(fr)-min(fr)})
rows.sort(key=lambda x:-x["roi"])
print("=== 按\033[1m利润(EV ROI)\033[0m排名 (真实价格模型) ===")
print("%-16s %4s %4s %8s %8s %s"%("变体","n","胜%","EV-ROI","总EV/窗","[3折ROI]"))
for i,r in enumerate(rows):
    fl="/".join("%+3.0f"%x for x in r["folds"]); flag="稳" if r["spread"]<8 else "波动"
    print("%s%-15s %4d %3.0f%% %+7.1f%% %+7.3f  [%s]%s"%("★" if i==0 else " ",r["v"],r["n"],r["win"],r["roi"],r["ev"]/r["n"],fl,flag))
print("\nEV-ROI = 利润/投入 (用真实标定价格模型). 注意: 胜率高≠ROI高 (贵的add胜率高但每股利润薄).")
print("price model: lead->真实成交价 (lead5→0.72, 8→0.79, 11→0.87, 20→0.91). 绝对值是proxy, 看相对排名.")
# === 执行边缘量化: 如果我们能比公允价便宜 D 分买到(eebde=+8c), EV如何? ===
def run_disc(D):
    res={v["n"]:[0.0,0.0,0] for v in VARIANTS}
    for k,win,path in WINS:
        for v in VARIANTS:
            r=sim(v,path)
            if not r: continue
            side,fills=r; won=(side==win); R=res[v["n"]]; R[2]+=1
            for ld,sh in fills:
                p=max(0.05,price(ld)-D); R[1]+=p*sh; R[0]+= sh*((1-p) if won else -p)
    return res
print("\n=== 执行边缘: 若能比公允价便宜 D 分买入 (eebde做到+8c), 各变体EV-ROI ===")
print("%-14s %s"%("变体"," ".join("D=%dc"%int(d*100) for d in (0,0.02,0.04,0.06,0.08))))
key=["winRateOpt","balanced","baseHeavy3","midPyr"]
for nm in key:
    out=[]
    for d in (0,0.02,0.04,0.06,0.08):
        R=run_disc(d)[nm]; out.append("%+5.1f%%"%(R[0]/R[1]*100 if R[1] else 0))
    print("%-14s %s"%(nm," ".join(out)))
print("\n→ 历史无订单簿, 答不了'能否买到便宜D分'. 这是\033[1m唯一剩下的真edge\033[0m, 只能 live maker 探针实测.")
