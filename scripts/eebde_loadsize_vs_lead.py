"""Bigger-sample version: across 169 windows (copy_cum_live, his final bet size + win), reconstruct the
underlying LEAD trajectory toward his favorite and ask: what lead behavior makes him end up HEAVY? Tests
whether his continue-to-heavy judgment = lead PERSISTENCE + STRENGTHENING + CLEANLINESS (low wobble)."""
import json,math,httpx,statistics
EF={}
for fn in ("data/copy_cum_live.jsonl","data/copy_cum.jsonl"):
    try:
        for l in open(fn,encoding="utf-8"):
            l=l.strip()
            if not l: continue
            try: r=json.loads(l)
            except: continue
            if r.get("slug") and r.get("side") and "win" in r and "final_cum" in r: EF[r["slug"]]=r
    except FileNotFoundError: pass
EF=list(EF.values())
sts=[int(r["slug"].split("-")[-1]) for r in EF]
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
def fetch(sym,lo,hi):
    out={};cur=lo
    while cur<hi:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=float(x[1])
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
BN={cn:fetch(SYM[cn],min(sts)-120,max(sts)+360) for cn in SYM}
recs=[]
for r in EF:
    coin="btc" if r["slug"].startswith("btc") else "eth"; st=int(r["slug"].split("-")[-1]); fav=r["side"]
    op=BN[coin].get(st)
    if not op: continue
    def lead(sec):
        p=BN[coin].get(st+sec)
        if not p: return None
        L=math.log(p/op)*1e4; return L if fav=="Up" else -L
    lp=[lead(s) for s in (60,120,180,240)]
    if any(x is None for x in lp): continue
    recs.append({"cum":r["final_cum"],"win":r["win"],
        "lead_final":lp[-1],"strengthen":lp[-1]-lp[0],"minlead":min(lp),"peak":max(lp),
        "clean":all(x>0 for x in lp)})   # lead stayed toward favorite whole way
print("窗口: %d\n"%len(recs))
def stat(rs,lbl):
    if not rs: print("  %-14s n=0"%lbl); return
    print("  %-14s n=%-3d 胜%2.0f%% | 末lead%+5.1f 走强%+5.1f 谷lead%+5.1f 峰lead%+5.1f 全程干净%2.0f%%"%(
        lbl,len(rs),sum(1 for r in rs if r["win"])/len(rs)*100,
        statistics.mean(r["lead_final"] for r in rs),statistics.mean(r["strengthen"] for r in rs),
        statistics.mean(r["minlead"] for r in rs),statistics.mean(r["peak"] for r in rs),
        sum(1 for r in rs if r["clean"])/len(rs)*100))
print("=== 按他最终下注额分档, 看lead行为 ===")
for lo,hi,lbl in ((0,800,"轻<800"),(800,1500,"800-1500"),(1500,3000,"1500-3000"),(3000,1e9,"重注>3000")):
    stat([r for r in recs if lo<=r["cum"]<hi],lbl)
print("\n=== 相关系数 (他下注额 vs lead特征) ===")
for k in ("lead_final","strengthen","minlead","peak"):
    xs=[r[k] for r in recs]; ys=[r["cum"] for r in recs]
    mx=statistics.mean(xs);my=statistics.mean(ys)
    cov=statistics.mean((x-mx)*(y-my) for x,y in zip(xs,ys));sx=statistics.pstdev(xs);sy=statistics.pstdev(ys)
    print("  下注额 vs %-11s: %+.3f"%(k,cov/(sx*sy) if sx*sy>0 else 0))
# 干净 vs 不干净
cl=[r for r in recs if r["clean"]]; ncl=[r for r in recs if not r["clean"]]
print("\n全程lead干净(没跌破favorite侧)的窗: 平均下注$%.0f, 胜%.0f%%"%(statistics.mean(r["cum"] for r in cl) if cl else 0,sum(1 for r in cl if r["win"])/len(cl)*100 if cl else 0))
print("lead中途wobble过的窗:           平均下注$%.0f, 胜%.0f%%"%(statistics.mean(r["cum"] for r in ncl) if ncl else 0,sum(1 for r in ncl if r["win"])/len(ncl)*100 if ncl else 0))
