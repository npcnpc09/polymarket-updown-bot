"""Can we RENT eebde's regime-proof selection as a single taker entry? His heavy bets sit on a
strong+strengthening+clean lead (final ~+30, strengthen ~+23, min-lead>0). Reconstruct that profile for
OUR DRY btc/eth 5m windows and check OUR win%/EV, SPLIT BY VOL. If our win-rate on the eebde-heavy
profile stays high across vol (like his), the profile itself is regime-proof and rentable. If it drops
in vol, his edge is the continuous averaging, not the profile."""
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
def pnl(r): return 5*(1-r["B"]) if r["won"] else -5*r["B"]
recs=[]
for r in ROWS:
    cn=r["coin"]; st=int(r["slug"].split("-")[-1]); op=BN[cn].get(st)
    if not op: continue
    side=r["side"]
    def lead(sec):
        p=BN[cn].get(st+sec)
        if not p: return None
        L=math.log(p/op)*1e4; return L if side=="Up" else -L
    # features ONLY up to ~180s (≈ our 167s entry, no lookahead); win = actual settle (recorded)
    lp=[lead(s) for s in (60,120,180)]
    if any(x is None for x in lp): continue
    cl=[BN[cn].get(st-60*i) for i in range(31)]; cl=[x for x in cl if x]
    vol=statistics.pstdev([math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))]) if len(cl)>=20 else None
    recs.append({"won":r["won"],"B":r["B"],"final":lp[-1],"strengthen":lp[-1]-lp[0],"minlead":min(lp),"vol":vol})
recs=[r for r in recs if r["vol"] is not None]
print("DRY 5m btc/eth (有lead+vol): %d\n"%len(recs))
def stat(rs,lbl):
    if not rs: print("  %-22s n=0"%lbl); return
    w=sum(1 for r in rs if r["won"]); ev=statistics.mean(pnl(r) for r in rs)
    print("  %-22s n=%-4d 胜%2.0f%% EV%+.2f 平均B%.2f"%(lbl,len(rs),w/len(rs)*100,ev,statistics.mean(r["B"] for r in rs)))
# eebde重注 profile: 强+渐强+干净
prof=[r for r in recs if r["final"]>=20 and r["strengthen"]>=10 and r["minlead"]>=0]
print("=== eebde重注profile (末lead>=20 & 走强>=10 & 全程干净) ===")
stat(recs,"全部DRY(基线)")
stat(prof,"符合eebde重注profile")
print("\n=== 该profile 按波动分档 (验证是否regime-proof) ===")
for lo,hi,lbl in ((0,8,"平静<8"),(8,12,"8-12"),(12,99,"高>=12")):
    stat([r for r in prof if lo<=r["vol"]<hi],"profile&"+lbl)
print("\n=== 对照: 不符profile 按波动 ===")
nprof=[r for r in recs if not(r["final"]>=20 and r["strengthen"]>=10 and r["minlead"]>=0)]
for lo,hi,lbl in ((0,8,"平静<8"),(8,12,"8-12"),(12,99,"高>=12")):
    stat([r for r in nprof if lo<=r["vol"]<hi],"非profile&"+lbl)
