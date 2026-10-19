"""DRY sim of 'maker loads eebde-style (add only while lead clean+holding), restricted to the regime-proof
profile'. ROBUST part (no fill-model): does conditional loading concentrate POSITION on winners, regime-
proof? = position($)-weighted win rate by vol. PRICE/EV is fill-model-estimated (flagged) — only real
money settles it. Compares vs naive lead>=5 (one unit per signal)."""
import json,math,httpx,statistics
ROWS=[]
for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if "won" in r and isinstance(r.get("B"),(int,float)) and r.get("coin")in("btc","eth") and "-5m-" in r.get("slug",""):
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
BN={cn:fetch(SYM[cn],min(sts)-2000,max(sts)+360) for cn in SYM}
def price_of(lead):  # rough favorite-price model from |lead| (fill-model estimate, NOT real)
    return max(0.5,min(0.97,0.5+0.013*abs(lead)))   # ~+1.3c per bp; lead20->0.76, lead30->0.89
sims=[]
for r in ROWS:
    cn=r["coin"]; st=int(r["slug"].split("-")[-1]); op=BN[cn].get(st)
    if not op: continue
    def px(sec):  # interpolate between minute-boundary klines
        t=st+sec; lo=(t//60)*60; hi=lo+60
        plo=BN[cn].get(lo); phi=BN[cn].get(hi)
        if plo is None: return None
        if phi is None: return plo
        f=(t-lo)/60.0; return plo*(1-f)+phi*f
    def L(sec):
        p=px(sec); return (math.log(p/op)*1e4) if p else None
    traj=[(s,L(s)) for s in (30,60,90,120,150,180)]
    traj=[(s,x) for s,x in traj if x is not None]
    if len(traj)<5: continue
    # eebde-style loading: side = sign at 60s; add a unit each checkpoint while lead toward side >=5 and
    # hasn't retraced >4 from its best-so-far (clean+holding). Stop adding once it wobbles.
    s60=next((x for s,x in traj if s==60),traj[0][1]); side=1 if s60>=0 else -1
    best=-99; units=0; cost=0.0; still=True
    for s,x in traj:
        ld=x*side
        if not still: continue
        if ld>=5 and ld>=best-4:
            units+=1; cost+=price_of(ld); best=max(best,ld)
        elif ld<best-4:
            still=False        # wobble -> stop adding (but hold what we have)
        best=max(best,ld)
    cl=[BN[cn].get(st-60*i) for i in range(31)]; cl=[x for x in cl if x]
    vol=statistics.pstdev([math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))]) if len(cl)>=20 else None
    if units==0 or vol is None: continue
    won = r["won"] if side==(1 if r["side"]=="Up" else -1) else (not r["won"])  # our side = leading side @60
    avgpx=cost/units
    pnl=units*((1-avgpx) if won else -avgpx)   # fill-model EV (estimated price)
    sims.append({"won":won,"units":units,"avgpx":avgpx,"pnl":pnl,"vol":vol})
print("模拟窗口: %d\n"%len(sims))
def report(rs,lbl):
    if not rs: print("  %-16s n=0"%lbl); return
    tu=sum(r["units"] for r in rs); wu=sum(r["units"] for r in rs if r["won"])
    eq_w=sum(1 for r in rs if r["won"])/len(rs)*100        # equal-weight win rate
    pos_w=wu/tu*100                                         # position($)-weight win rate (ROBUST)
    avgpx=sum(r["avgpx"]*r["units"] for r in rs)/tu
    pnl=sum(r["pnl"] for r in rs)
    print("  %-16s n=%-4d 等权胜%2.0f%% | 仓位加权胜%2.0f%% 均价~%.2f 估EV/窗$%+.2f"%(lbl,len(rs),eq_w,pos_w,avgpx,pnl/len(rs)*5/ max(1,statistics.mean(r['units'] for r in rs)) if rs else 0))
print("=== 仓位加权胜率(robust) + 估算EV(fill-model, 仅参考) ===")
report(sims,"全部(lead>=5起)")
print("\n=== 按波动分档 (仓位加权胜率是否regime-proof) ===")
for lo,hi,lbl in ((0,8,"平静<8"),(8,12,"8-12"),(12,99,"高>=12")):
    report([r for r in sims if lo<=r["vol"]<hi],lbl)
# 重仓窗口(units>=4 = 持续加成了重注) vs 轻仓
print("\n=== 重仓(units>=4,=eebde式确认) vs 轻仓(units<=2) ===")
report([r for r in sims if r["units"]>=4],"重仓units>=4")
report([r for r in sims if r["units"]<=2],"轻仓units<=2")
