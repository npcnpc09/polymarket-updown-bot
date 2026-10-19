"""Cached evolution engine — fetch 1s lead paths ONCE (data/lead_paths.json), then every generation runs
INSTANTLY on the cache. Gen-3: ~28 fine variants around the winner (tight base + strict strengthen + heavy
pyramid), ranked by capital-weighted win rate with 3-FOLD cross-validation (stable across all 3 folds = not
luck). Edit VARIANTS and re-run for next gens (cache reused). (Selection/win-rate half; EV needs live DRY.)"""
import json,os,math,statistics
import httpx
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE=os.path.join(ROOT,"data","lead_paths.json"); SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}; OUT=["Up","Down"]
NWIN=600
# ---------- build/load cache ----------
def build_cache():
    c=httpx.Client(timeout=20,headers={"User-Agent":"Mozilla/5.0"})
    RW={}
    for l in open(os.path.join(ROOT,"data","ce25_full.jsonl"),encoding="utf-8"):
        r=json.loads(l); s=r.get("slug","")
        if "updown" not in s or "-5m-" not in s: continue
        w=RW.setdefault(s,{"buys":[],"ridx":None,"rsize":0.0})
        if r.get("type")=="TRADE" and r.get("side","").upper()=="BUY": w["buys"].append((r.get("outcome"),r.get("size") or 0))
        elif r.get("type")=="REDEEM":
            w["rsize"]+=r.get("size") or 0
            if r.get("outcomeIndex") is not None: w["ridx"]=r.get("outcomeIndex")
    def winner(w):
        if w["ridx"] in (0,1): return OUT[w["ridx"]]
        if w["rsize"]>0:
            up=sum(z for o,z in w["buys"] if o=="Up"); dn=sum(z for o,z in w["buys"] if o=="Down")
            return "Up" if abs(w["rsize"]-up)<abs(w["rsize"]-dn) else "Down"
        return None
    wins=[]
    for s,w in RW.items():
        parts=s.split("-"); coin=parts[0]
        if coin not in SYM: continue
        try: st=int(parts[-1])
        except: continue
        win=winner(w)
        if win: wins.append((coin,st,win))
    wins.sort(key=lambda x:-x[1]); wins=wins[:NWIN]
    print("拉 %d 窗的1秒lead路径(一次性)..."%len(wins))
    cache={}
    for i,(coin,st,win) in enumerate(wins):
        try:
            k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1s","startTime":st*1000,"endTime":(st+260)*1000,"limit":1000}).json()
            if not isinstance(k,list) or len(k)<60: continue
            op=float(k[0][1]); path={str(int(x[0]//1000)-st):round(math.log(float(x[4])/op)*1e4,2) for x in k}
            cache["%s|%d"%(coin,st)]={"win":win,"lead":path}
        except: continue
        if i%100==0 and i: print("  ...%d"%i)
    json.dump(cache,open(CACHE,"w"))
    print("已缓存 %d 窗 -> %s\n"%(len(cache),CACHE))
    return cache
cache=json.load(open(CACHE)) if os.path.exists(CACHE) else build_cache()
WINS=[(k,v["win"],v["lead"]) for k,v in cache.items()]
print("缓存窗口 %d\n"%len(WINS))
# ---------- variant spec + sim ----------
def V(n,gt=8,offlo=15,offhi=70,checks=(90,150,210),agt=12,rt=3,sizes=(1,8,16),strq=5,accel=None):
    return dict(n=n,gt=gt,offlo=offlo,offhi=offhi,checks=list(checks),agt=agt,rt=rt,sizes=list(sizes),strq=strq,accel=accel)
def lead(path,off):
    for o in range(off,off+8):
        if str(o) in path: return path[str(o)]
    return None
def sim(v,path):
    side=lb=peak=None; fills=[];
    for off in range(v["offlo"],v["offhi"]+1,3):
        l=lead(path,off)
        if l is None: continue
        if abs(l)>=v["gt"]: side="Up" if l>=0 else "Down"; lb=abs(l); peak=abs(l); fills.append(v["sizes"][0]); break
    if side is None: return None
    ai=1
    for off in v["checks"]:
        if ai>=len(v["sizes"]): break
        l=lead(path,off)
        if l is None: continue
        lt=l*(1 if side=="Up" else -1)
        if lt>peak: peak=lt
        if peak-lt>v["rt"]: break
        if lt<lb+v["strq"] or lt<v["agt"]: continue
        if v["accel"] is not None:
            lp=lead(path,off-30)
            if lp is None or (lt-lp*(1 if side=="Up" else -1))<v["accel"]: continue
        fills.append(v["sizes"][ai]); ai+=1
    return side,sum(fills),len(fills)
# ---------- GEN-3 variants: fine around tight+strict+pyramid ----------
VARIANTS=[V("anchor_ST2",gt=8,sizes=(1,8,16),agt=12,strq=5), V("A_base",gt=5,sizes=(5,5,5),agt=8,strq=0), V("G_baseOnly",gt=5,sizes=(5,),checks=(),agt=99,strq=0)]
for gt in (8,10,12):
    for strq in (3,5,7):
        for sz in ((1,8,16),(1,6,12,20),(1,10,25)):
            VARIANTS.append(V("g%d_s%d_p%s"%(gt,strq,"".join(str(x) for x in sz)),gt=gt,strq=strq,sizes=sz,agt=max(10,gt+2)))
# trim to ~30 (keep anchors + a spread)
seen=set(); VV=[]
for v in VARIANTS:
    if v["n"] in seen: continue
    seen.add(v["n"]); VV.append(v)
VARIANTS=VV[:33]
# ---------- run + 3-fold CV ----------
import random
idx=list(range(len(WINS)));
folds=[WINS[i::3] for i in range(3)]
def run(subset):
    res={v["n"]:[0.0,0.0,0,0,0,0] for v in VARIANTS}
    for k,win,path in subset:
        for v in VARIANTS:
            r=sim(v,path)
            if not r: continue
            sd,sh,nf=r; won=(sd==win); R=res[v["n"]]
            R[1]+=sh; R[2]+=1; R[3]+=1 if won else 0
            if won: R[0]+=sh
            if nf>=3: R[4]+=1; R[5]+=1 if won else 0
    return res
full=run(WINS); F=[run(f) for f in folds]
def cww(R): return R[0]/R[1]*100 if R[1] else 0
rows=[]
for v in VARIANTS:
    R=full[v["n"]]
    if R[2]==0: continue
    fv=[cww(F[i][v["n"]]) for i in range(3)]
    rows.append({"v":v["n"],"n":R[2],"win":R[3]/R[2]*100,"cww":cww(R),"folds":fv,"spread":max(fv)-min(fv),"hw":R[5]/R[4]*100 if R[4] else None,"hn":R[4]})
rows.sort(key=lambda x:-x["cww"])
print("=== Gen-3 (缓存秒出, 3折交叉验证) Top 16 ===")
print("%-20s %4s %4s %7s %s %s"%("变体","n","胜%","资金权胜%","[3折] spread","重仓胜%/n"))
for i,r in enumerate(rows[:16]):
    hw="%2.0f%%/%d"%(r["hw"],r["hn"]) if r["hw"] is not None else "—"
    fl="/".join("%2.0f"%x for x in r["folds"])
    flag="稳" if r["spread"]<7 else "波动"
    print("%s%-19s %4d %3.0f%% %6.0f%%  [%s]%s %s"%("★" if i==0 else " ",r["v"],r["n"],r["win"],r["cww"],fl,flag,hw))
print("\n命名 g{base门}_s{strq}_p{pyramid}. spread=3折最大-最小, <7=稳(非运气). G_baseOnly=单发地板.")
