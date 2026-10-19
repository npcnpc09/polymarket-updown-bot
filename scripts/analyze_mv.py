"""Rank the DRY variants (data/mv_dry.jsonl). Per variant: n windows, win%, blended avg price, account-EV
ROI, and the KEY eebde metric — win% of HEAVY windows (>=2 adds = strengtheners). All variants saw identical
windows (OOS-fair). Report sorted by ROI; flag the leader. (binance outcomes — reliable on favorite side.)"""
import json,os,statistics
from collections import defaultdict
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
f=os.path.join(ROOT,"data","mv_dry.jsonl")
rows=[json.loads(l) for l in open(f,encoding="utf-8")] if os.path.exists(f) else []
if not rows: print("还没数据 (5m窗口结算需~5分钟)"); raise SystemExit
byv=defaultdict(list)
for r in rows: byv[r["v"]].append(r)
nwin=len(set(r["slug"] for r in rows))
print("已结算窗口 ~%d | 变体 %d 个 (同一批窗口, OOS公平)\n"%(nwin,len(byv)))
res=[]
for v,g in byv.items():
    w=sum(1 for r in g if r["won"]); cost=sum(r["avg_px"]*r["shares"] for r in g); pnl=sum(r["pnl"] for r in g)
    heavy=[r for r in g if r["n_fills"]>=3]; hw=(sum(1 for r in heavy if r["won"])/len(heavy)*100) if heavy else None
    res.append({"v":v,"n":len(g),"win":w/len(g)*100,"avg":statistics.mean(r["avg_px"] for r in g),"roi":pnl/cost*100 if cost else 0,"pnl":pnl,"nh":len(heavy),"hw":hw})
res.sort(key=lambda x:-x["roi"])
print("%-15s %4s %5s %6s %7s %8s %s"%("变体","n","胜%","均价","账面ROI","盈亏$","重仓(>=2加)胜%/n"))
for i,r in enumerate(res):
    lead="★" if i==0 else " "
    hw="%2.0f%%/%d"%(r["hw"],r["nh"]) if r["hw"] is not None else "—/0"
    print("%s%-14s %4d %4.0f%% %6.3f %+6.1f%% %+8.1f  %s"%(lead,r["v"],r["n"],r["win"],r["avg"],r["roi"],r["pnl"],hw))
print("\n=== 各币表现 (哪些币edge成立) ===")
byc=defaultdict(list)
for r in rows: byc[r.get("coin","?")].append(r)
for coin in ("btc","eth","sol","xrp","doge"):
    g=byc.get(coin)
    if g:
        w=sum(1 for r in g if r["won"]); cost=sum(r["avg_px"]*r["shares"] for r in g); pf=sum(r["pnl"] for r in g)
        print("  %-5s n=%-4d 胜%2.0f%% 均价%.3f 账面ROI%+6.1f%%"%(coin,len(g),w/len(g)*100,statistics.mean(r["avg_px"] for r in g),pf/cost*100 if cost else 0))
nh=sum(1 for r in rows if r["n_fills"]>=3)
print("\n重仓窗(>=2加)总数: %d  (=0 说明还没遇到趋势段, 变体没分化)"%nh)
print("判定标准: ROI正 + 重仓胜率~90% + 跨regime+跨币稳. 要更多窗口+趋势段, 现在别急定.")
