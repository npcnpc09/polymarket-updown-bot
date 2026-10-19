"""Does eebde sometimes commit BIG immediately (not gradual scale-in)? Per btc/eth 5m window:
biggest single trade, time his favorite cum reaches $3000, whether it's an EARLY big commitment.
Check if early-big windows win MORE (his highest-conviction = best?)."""
import json,re,httpx,math,statistics
from collections import defaultdict
EF="data/eebde_history_7d.jsonl"
WT=defaultdict(list)
for ln in open(EF,encoding="utf-8"):
    ln=ln.strip()
    if not ln: continue
    try: r=json.loads(ln)
    except: continue
    if r.get("type")!="TRADE" or (r.get("side") or "").upper()!="BUY": continue
    m=re.match(r"(btc|eth)-updown-5m-(\d+)",r.get("slug","") or "")
    if not m or r.get("outcome") not in ("Up","Down"): continue
    WT[r["slug"]].append((r.get("timestamp",0),r.get("outcome"),r.get("price",0) or 0,r.get("size",0) or 0,(r.get("usdcSize",0) or 0)))
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}; sts=[int(s.split("-")[-1]) for s in WT]
def bn(sym,t0,t1):
    out={};cur=t0
    while cur<t1:
        k=httpx.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":t1*1000,"limit":1000},timeout=20).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[4]))
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
BN={c:bn(SYM[c],min(sts)-120,max(sts)+400) for c in SYM}
def winner(slug):
    c="btc" if slug.startswith("btc") else "eth"; st=int(slug.split("-")[-1]); d=BN[c]
    o=d.get(st) or d.get(st+1); cl=d.get(st+240) or d.get(st+300)
    return ("Up" if cl[1]>=o[0] else "Down") if (o and cl) else None
rows=[]
for slug,trs in WT.items():
    w=winner(slug)
    if not w: continue
    st=int(slug.split("-")[-1]); trs.sort(key=lambda x:x[0])
    cum=defaultdict(float); maxsingle=0; t3000=None; favatend=None
    for ts,o,p,sz,usd in trs:
        cum[o]+=usd; maxsingle=max(maxsingle,usd)
        fav=max(cum,key=cum.get)
        if t3000 is None and cum[fav]>=3000: t3000=ts-st
    fav=max(cum,key=cum.get)
    rows.append({"win":fav==w,"maxsingle":maxsingle,"t3000":t3000,"favval":cum[fav]})
print("窗口:",len(rows),"\n")
def wr(rs): return sum(1 for r in rs if r["win"])/len(rs)*100 if rs else 0
print("=== 单笔最大买单 vs 胜率 ===")
for lo,hi in ((0,500),(500,1000),(1000,2000),(2000,3000),(3000,1e9)):
    s=[r for r in rows if lo<=r["maxsingle"]<hi]
    if s: print("  单笔 $%-5d-%-6s: n=%-4d 胜%2.0f%%"%(lo,("%d"%hi if hi<1e9 else "+"),len(s),wr(s)))
print("\n=== 到$3000的速度 vs 胜率 (一上来就大?) ===")
reached=[r for r in rows if r["t3000"] is not None]
print("  到达$3000的窗口: %d / %d"%(len(reached),len(rows)))
for lo,hi in ((0,60),(60,120),(120,200),(200,400)):
    s=[r for r in reached if lo<=r["t3000"]<hi]
    if s: print("  %3d-%-3ds 内到$3000: n=%-4d 胜%2.0f%%"%(lo,hi,len(s),wr(s)))
never=[r for r in rows if r["t3000"] is None]
print("  从没到$3000:        n=%-4d 胜%2.0f%%"%(len(never),wr(never)))
print("\n=== '一上来就大' (60秒内单笔>=2000 或 90秒内到$3000) vs 其余 ===")
big=[r for r in rows if r["maxsingle"]>=2000 or (r["t3000"] is not None and r["t3000"]<90)]
rest=[r for r in rows if not (r["maxsingle"]>=2000 or (r["t3000"] is not None and r["t3000"]<90))]
print("  早重仓: n=%-4d 胜%2.0f%%  | 其余: n=%-4d 胜%2.0f%%"%(len(big),wr(big),len(rest),wr(rest)))
