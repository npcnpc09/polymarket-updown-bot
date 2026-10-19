"""Test the premise 'eebde makes money in ALL regimes'. Take his per-window favorite + bet size +
win (copy_cum_live.jsonl), compute BTC vol at each window, and split HIS favorite win-rate by vol band
AND by bet size. If his win-rate stays high in choppy/high-vol regimes (where OUR win rate drops), he is
regime-proof and the mechanism is SELECTION. Compare against our DRY win-rate in the same windows."""
import json,math,httpx,statistics
EF=[]
for fn in ("data/copy_cum_live.jsonl","data/copy_cum.jsonl"):
    try:
        for l in open(fn,encoding="utf-8"):
            l=l.strip()
            if not l: continue
            try: r=json.loads(l)
            except: continue
            if r.get("slug") and r.get("side") and "win" in r:
                EF.append(r)
    except FileNotFoundError: pass
# dedup by slug (keep last)
seen={};
for r in EF: seen[r["slug"]]=r
EF=list(seen.values())
print("eebde 有favorite+输赢的窗口: %d"%len(EF))
sts=[int(r["slug"].split("-")[-1]) for r in EF]
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
def fetch(sym,lo,hi):
    out={};cur=lo
    while cur<hi:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=float(x[4])
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
BTC=fetch("BTCUSDT",min(sts)-2000,max(sts)+360)
def vol30(st):
    cl=[BTC.get(st-60*i) for i in range(31)]; cl=[x for x in cl if x]
    if len(cl)<20: return None
    return statistics.pstdev([math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))])
for r in EF: r["vol"]=vol30(int(r["slug"].split("-")[-1]))
EF=[r for r in EF if r["vol"] is not None]
def wr(rs): return sum(1 for r in rs if r["win"])/len(rs)*100 if rs else 0
print("\neebde整体: 窗口%d favorite胜率 %.0f%%"%(len(EF),wr(EF)))
print("\n=== 他的favorite胜率 按BTC波动分档 (验证regime-proof) ===")
for lo,hi,lbl in ((0,6,"平静<6"),(6,9,"6-9"),(9,13,"9-13"),(13,99,"高>13")):
    b=[r for r in EF if lo<=r["vol"]<hi]
    if b: print("  %-10s n=%-3d 他favorite胜%2.0f%%"%(lbl,len(b),wr(b)))
print("\n=== 按他的下注额(final_cum) 分, 再看胜率 ===")
for lo,hi,lbl in ((0,500,"轻<500"),(500,1500,"500-1500"),(1500,3000,"1500-3000"),(3000,1e9,"重注>3000")):
    b=[r for r in EF if lo<=r.get("final_cum",0)<hi]
    if b: print("  %-12s n=%-3d 胜%2.0f%% 平均vol%.1f"%(lbl,len(b),wr(b),statistics.mean(r["vol"] for r in b)))
print("\n=== 重注(>=1500) 在不同波动下还稳吗 ===")
heavy=[r for r in EF if r.get("final_cum",0)>=1500]
for lo,hi,lbl in ((0,8,"平静<8"),(8,99,"高>=8")):
    b=[r for r in heavy if lo<=r["vol"]<hi]
    if b: print("  重注&%s: n=%-3d 胜%2.0f%%"%(lbl,len(b),wr(b)))
