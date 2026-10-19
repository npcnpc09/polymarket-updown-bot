"""Backtest 'confirm Coinbase lead with binance'. Use engine DRY z>=2.5 entries (REAL Coinbase lead +
REAL settlement won); reconstruct the BINANCE lead at ~entry(165s) toward the engine's side. Bucket by
how much binance CONFIRMS: diverges(<0)/weak(0-5)/confirms(>=5). Compare win%/EV, AND per-DAY OOS (entry
filters die here). If 'binance diverges' is consistently -EV every day -> the confirm-filter is real;
if it flips per day or cuts winners -> overfit like every other entry filter."""
import json,math,httpx,statistics,datetime
ROWS=[]
for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if "won" in r and isinstance(r.get("B"),(int,float)) and r.get("coin")in("btc","eth") and "-5m-" in r.get("slug","") and isinstance(r.get("lead"),(int,float)):
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
def pxat(cn,t):
    lo=(t//60)*60; hi=lo+60; a=BN[cn].get(lo); b=BN[cn].get(hi)
    if a is None: return None
    if b is None: return a
    f=(t-lo)/60.0; return a*(1-f)+b*f
def pnl(r): return 5*(1-r["B"]) if r["won"] else -5*r["B"]
recs=[]
for r in ROWS:
    cn=r["coin"]; st=int(r["slug"].split("-")[-1])
    # reconstruct z>=2.5 filter (same as the live gate)
    cl=[BN[cn].get(st-60*i) for i in range(31)]; cl=[x for x in cl if x]
    if len(cl)<20: continue
    vol=statistics.pstdev([math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))])
    if vol<=0 or abs(r["lead"])/vol < 2.5: continue
    op=pxat(cn,st); p165=pxat(cn,st+165)
    if op is None or p165 is None: continue
    side=1 if r["side"]=="Up" else -1
    binlead=math.log(p165/op)*1e4*side          # binance lead toward the engine's side at ~165s
    recs.append({"won":r["won"],"B":r["B"],"binlead":binlead,"cblead":abs(r["lead"]),
                 "day":datetime.datetime.utcfromtimestamp(st).strftime("%m-%d")})
def s(rs):
    if not rs: return "n=0"
    w=sum(1 for r in rs if r["won"]); ev=statistics.mean(pnl(r) for r in rs)
    return "n=%-3d 胜%2.0f%% EV%+.2f"%(len(rs),w/len(rs)*100,ev)
print("z>=2.5 重建样本: %d (这些是我们实际会下的单)\n"%len(recs))
print("=== 按 binance 对我方lead 的确认程度 ===")
print("  binance背离(<0):   %s"%s([r for r in recs if r["binlead"]<0]))
print("  binance弱(0-5):    %s"%s([r for r in recs if 0<=r["binlead"]<5]))
print("  binance确认(5-15): %s"%s([r for r in recs if 5<=r["binlead"]<15]))
print("  binance强确认(>=15):%s"%s([r for r in recs if r["binlead"]>=15]))
print("\n=== 核心: binance确认(>=5) vs 不确认(<5) ===")
conf=[r for r in recs if r["binlead"]>=5]; noconf=[r for r in recs if r["binlead"]<5]
print("  确认>=5:  %s"%s(conf))
print("  不确认<5: %s"%s(noconf))
print("\n=== 按天 OOS: 不确认(<5) 是否每天都差 ===")
days=sorted(set(r["day"] for r in recs))
for d in days:
    dd=[r for r in recs if r["day"]==d]
    print("  %s | 不确认<5: %-22s | 确认>=5: %s"%(d,s([r for r in dd if r["binlead"]<5]),s([r for r in dd if r["binlead"]>=5])))
