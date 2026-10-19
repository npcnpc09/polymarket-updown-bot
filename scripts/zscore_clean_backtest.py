"""Clean taker backtest of the z-score gate, using the ENGINE's OWN recorded entries (side/B/won/lead)
so price & side are internally consistent (no reconstruction mismatch). z = |engine entry lead| / vol
(vol = prior-30m realized, reconstructed). Report z>=2.5 vs z<2.5 per day + overall + frequency."""
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
BN={cn:fetch(SYM[cn],min(sts)-2000,max(sts)+60) for cn in SYM}
def pnl(r): return 5*(1-r["B"]) if r["won"] else -5*r["B"]
recs=[]
for r in ROWS:
    cn=r["coin"]; st=int(r["slug"].split("-")[-1])
    cl=[BN[cn].get(st-60*i) for i in range(31)]; cl=[x for x in cl if x]
    if len(cl)<20: continue
    vol=statistics.pstdev([math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))])
    if vol<=0: continue
    z=abs(r["lead"])/vol
    recs.append({"won":r["won"],"B":r["B"],"z":z,"vol":vol,"lead":abs(r["lead"]),
                 "day":datetime.datetime.utcfromtimestamp(st).strftime("%m-%d")})
def s(rs):
    if not rs: return "n=0"
    w=sum(1 for r in rs if r["won"]); ev=statistics.mean(pnl(r) for r in rs)
    return "n=%-4d 胜%2.0f%% EV%+.2f 总$%+.1f B%.2f"%(len(rs),w/len(rs)*100,ev,sum(pnl(r) for r in rs),statistics.mean(r["B"] for r in rs))
print("总窗口: %d\n"%len(recs))
print("=== z分档 (引擎真实入场) ===")
for lo,hi,lbl in ((0,1.5,"z<1.5"),(1.5,2.5,"z1.5-2.5"),(2.5,4,"z2.5-4"),(4,99,"z>=4")):
    print("  %-10s %s"%(lbl,s([r for r in recs if lo<=r["z"]<hi])))
print("\n=== z>=2.5 按天 OOS ===")
days=sorted(set(r["day"] for r in recs))
for d in days:
    dd=[r for r in recs if r["day"]==d]
    print("  %s | z>=2.5: %-34s | z<2.5: %s"%(d,s([r for r in dd if r["z"]>=2.5]),s([r for r in dd if r["z"]<2.5])))
print("  合计   | z>=2.5: %-34s | z<2.5: %s"%(s([r for r in recs if r["z"]>=2.5]),s([r for r in recs if r["z"]<2.5])))
# frequency
span=(max(int(r2["slug"].split("-")[-1]) for r2 in ROWS)-min(int(r2["slug"].split("-")[-1]) for r2 in ROWS))/86400
nz=sum(1 for r in recs if r["z"]>=2.5)
print("\n频率: z>=2.5 共%d窗 / %.1f天 = %.0f窗/天 (btc+eth 5m)"%(nz,span,nz/span if span>0 else 0))
print("对照: z>=2.0 = %d窗 (%.0f/天), z>=3.0 = %d窗"%(sum(1 for r in recs if r["z"]>=2),sum(1 for r in recs if r["z"]>=2)/span if span>0 else 0,sum(1 for r in recs if r["z"]>=3)))