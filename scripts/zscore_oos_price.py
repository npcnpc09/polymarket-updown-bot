"""Decisive check on the lead Z-score (lead/vol) signal: (1) per-DAY OOS — does z>=2.5 win consistently
each day or is it one-day overfit? (2) PRICE — what B do high-z windows enter at, split by vol? If calm
high-z entries are CHEAP (low B) yet win ~100%, that's a real cheap+regime-proof edge (vs the priced-in
abs-lead profile at B~0.91)."""
import json,math,httpx,statistics,datetime
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
    p180=BN[cn].get(st+180)
    if not p180: continue
    lead=abs(math.log(p180/op)*1e4); side=1 if math.log(p180/op)>=0 else -1
    cl=[BN[cn].get(st-60*i) for i in range(31)]; cl=[x for x in cl if x]
    if len(cl)<20: continue
    vol=statistics.pstdev([math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))])
    if vol<=0 or lead<5: continue
    won = r["won"] if side==(1 if r["side"]=="Up" else -1) else (not r["won"])
    recs.append({"won":won,"B":r["B"],"z":lead/vol,"vol":vol,"lead":lead,
        "day":datetime.datetime.utcfromtimestamp(st).strftime("%m-%d")})
def s(rs):
    if not rs: return "n=0"
    w=sum(1 for r in rs if r["won"]); ev=statistics.mean(pnl(r) for r in rs)
    return "n=%-3d 胜%2.0f%% EV%+.2f B%.2f"%(len(rs),w/len(rs)*100,ev,statistics.mean(r["B"] for r in rs))
days=sorted(set(r["day"] for r in recs))
print("=== z>=2.5 按天 OOS ===")
for d in days:
    dd=[r for r in recs if r["day"]==d]
    print("  %s | z>=2.5: %-28s | z<2.5: %s"%(d,s([r for r in dd if r["z"]>=2.5]),s([r for r in dd if r["z"]<2.5])))
print("  合计   | z>=2.5: %-28s | z<2.5: %s"%(s([r for r in recs if r["z"]>=2.5]),s([r for r in recs if r["z"]<2.5])))
print("\n=== 高-z 入场价(B) 按波动 — 够不够便宜 ===")
hz=[r for r in recs if r["z"]>=2.5]
for lo,hi,lbl in ((0,8,"平静<8"),(8,12,"8-12"),(12,99,"高>=12")):
    b=[r for r in hz if lo<=r["vol"]<hi]
    if b: print("  %-10s z>=2.5: n=%-3d 胜%2.0f%% 平均lead%.0f 平均B%.2f EV%+.2f"%(lbl,len(b),sum(1 for r in b if r["won"])/len(b)*100,statistics.mean(r["lead"] for r in b),statistics.mean(r["B"] for r in b),statistics.mean(pnl(r) for r in b)))
print("\n参考: 绝对lead>=20 profile 平均B~0.91(贵). 看高-z在平静市B是否更低=更便宜的同质赢家")