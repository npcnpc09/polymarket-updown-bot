"""BTC-only signals (BTC moves independent of Polymarket, so the edge must be in BTC's own action).
Test two regime-proof candidates at entry (~180s), no lookahead, vs 5m settlement:
 1) higher-TF TREND alignment: does the 5m lead align with the prior 30m/60m BTC trend?
 2) lead Z-SCORE = lead/vol (vol-normalized): a +20 lead is 4-sigma in calm, 1-sigma in wild.
Split win% by vol to check regime-proofness. The prize = a signal that predicts persistence AND holds
across vol AND can act earlier/cheaper than the absolute-lead profile."""
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
BN={cn:fetch(SYM[cn],min(sts)-4000,max(sts)+360) for cn in SYM}
def pnl(r): return 5*(1-r["B"]) if r["won"] else -5*r["B"]
recs=[]
for r in ROWS:
    cn=r["coin"]; st=int(r["slug"].split("-")[-1]); op=BN[cn].get(st)
    if not op: continue
    p180=BN[cn].get(st+180)
    if not p180: continue
    lead180=math.log(p180/op)*1e4; side=1 if lead180>=0 else -1
    # vol (prior 30m, 1-min)
    cl=[BN[cn].get(st-60*i) for i in range(31)]; cl=[x for x in cl if x]
    if len(cl)<20: continue
    vol=statistics.pstdev([math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))])
    if vol<=0: continue
    # higher-TF trend (prior 30m / 60m net move), aligned with the 5m leading side
    t30=BN[cn].get(st-1800); t60=BN[cn].get(st-3600)
    tr30=(math.log(op/t30)*1e4) if t30 else None
    tr60=(math.log(op/t60)*1e4) if t60 else None
    align30 = (tr30 is not None and (tr30*side>0))
    align60 = (tr60 is not None and (tr60*side>0))
    won = r["won"] if side==(1 if r["side"]=="Up" else -1) else (not r["won"])
    recs.append({"won":won,"B":r["B"],"lead":abs(lead180),"z":abs(lead180)/vol,"vol":vol,
        "tr30a":tr30*side if tr30 is not None else None,"align30":align30,"align60":align60})
recs=[r for r in recs if r["lead"]>=5]   # only meaningful leads (our entry zone)
print("窗口(lead>=5): %d\n"%len(recs))
def stat(rs,lbl):
    if not rs: print("  %-20s n=0"%lbl); return
    w=sum(1 for r in rs if r["won"]); ev=statistics.mean(pnl({"won":r["won"],"B":r["B"]}) for r in rs)
    print("  %-20s n=%-4d 胜%2.0f%% EV%+.2f"%(lbl,len(rs),w/len(rs)*100,ev))
print("=== 1) 高周期趋势对齐 (5m领先 vs 前30m/60m趋势) ===")
stat([r for r in recs if r["align30"]],"对齐30m趋势")
stat([r for r in recs if not r["align30"]],"逆30m趋势")
stat([r for r in recs if r["align30"] and r["align60"]],"对齐30m+60m")
print("\n  对齐30m+60m 按波动:")
both=[r for r in recs if r["align30"] and r["align60"]]
for lo,hi,lbl in ((0,8,"平静<8"),(8,12,"8-12"),(12,99,"高>=12")): stat([r for r in both if lo<=r["vol"]<hi],"  "+lbl)
print("\n=== 2) lead Z-score (lead/vol) 分档 ===")
for lo,hi,lbl in ((0,1.5,"z<1.5"),(1.5,2.5,"z1.5-2.5"),(2.5,4,"z2.5-4"),(4,99,"z>=4 强")):
    stat([r for r in recs if lo<=r["z"]<hi],lbl)
print("\n  z>=2.5 按波动 (regime-proof?):")
hz=[r for r in recs if r["z"]>=2.5]
for lo,hi,lbl in ((0,8,"平静<8"),(8,12,"8-12"),(12,99,"高>=12")): stat([r for r in hz if lo<=r["vol"]<hi],"  "+lbl)
