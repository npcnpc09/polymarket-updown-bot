"""Analyze maker losing fills: windows with n_L>0 in early_maker_live.jsonl. For each, pull from the
log the bid(s) we placed (side, price, lead-at-bid, checkpoint), and reconstruct the lead path from
binance (open vs 30/60/.../settle) to see if it was a FADE/REVERSAL/WHIPSAW. Compare losers vs winners
on: entry lead, avg_px, 5m/15m, peak-lead-then-reverse."""
import json,re,math,httpx
from collections import defaultdict
ROWS=[]
for l in open("data/early_maker_live.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: ROWS.append(json.loads(l))
    except: pass
losers=[r for r in ROWS if r["n_L"]>0]
winners=[r for r in ROWS if r["n_L"]==0 and r["n_W"]>0]
# parse log for bids: "*** MAKER-BID #n {slug} {side} 5sh @ {px} (lead{+d}) ..."
BID=defaultdict(list)
for fn in ("data/early_maker_live.log","data/eml.out"):
    try:
        for line in open(fn,encoding="utf-8"):
            m=re.search(r"MAKER-BID #\d+ (\S+) (Up|Down) \dsh @ ([\d.]+) \(lead([+-]?\d+)\)",line)
            if m: BID[m.group(1)].append({"side":m.group(2),"px":float(m.group(3)),"lead":int(m.group(4))})
    except FileNotFoundError: pass
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
c=httpx.Client(timeout=20,headers={"User-Agent":"Mozilla/5.0"})
def leadpath(coin,st,dur):
    sym=SYM[coin]
    try:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":(st)*1000,"endTime":(st+dur+60)*1000,"limit":20}).json()
        d={int(x[0]//1000):(float(x[1]),float(x[4])) for x in k}
    except: return []
    op=d.get(st,[None,None])[0]
    if not op: return []
    out=[]
    for off in range(0,dur+1,60):
        p=d.get(st+off)
        out.append(round(math.log(p[1]/op)*1e4,0) if p else None)
    return out
print("亏损窗口: %d个 (含%d个输侧成交)\n"%(len(losers),sum(r["n_L"] for r in losers)))
for r in losers:
    slug=r["slug"]; coin=r["coin"]; st=int(slug.split("-")[-1])
    dur=900 if "-15m-" in slug else 300
    bids=BID.get(slug,[])
    lp=leadpath(coin,st,dur)
    print("● %s  赢家=%s 我们填%s侧"%(slug,r["winner"],"/".join(set(b["side"] for b in bids)) or "?"))
    print("   成交 W%d/L%d 均价%.3f PnL$%+.2f"%(r["n_W"],r["n_L"],r["avg_px"],r["pnl"]))
    if bids:
        for b in bids: print("   挂单: %s @%.2f (挂时lead%+d → 我们押的这侧%s)"%(b["side"],b["px"],b["lead"],"赢" if b["side"]==r["winner"] else "亏***"))
    print("   lead路径(每分钟,正=我们最初领先侧): %s"%("/".join(str(int(x)) if x is not None else "·" for x in lp)))
    print()
# 对比
def stat(rs,lbl):
    if not rs: return
    apx=sum(r["avg_px"]*r["n_filled"] for r in rs)/sum(r["n_filled"] for r in rs)
    leads=[b["lead"] for r in rs for b in BID.get(r["slug"],[])]
    al=sum(abs(x) for x in leads)/len(leads) if leads else 0
    print("%-8s n=%d 均价%.3f 挂时|lead|均%.1f"%(lbl,len(rs),apx,al))
print("=== 输窗 vs 赢窗 对比 ===")
stat(losers,"输窗"); stat(winners,"赢窗")
