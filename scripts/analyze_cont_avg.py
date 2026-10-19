import json,os,statistics
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
f=os.path.join(ROOT,"data","cont_avg_bot.jsonl")
rows=[json.loads(l) for l in open(f,encoding="utf-8")] if os.path.exists(f) else []
rows=[r for r in rows if r.get("won") is not None]
if not rows:
    print("还没结算行 (DRY 5m窗口结算需要~5分钟)"); raise SystemExit
w=sum(1 for r in rows if r["won"]); cost=sum(r["avg_px"]*r["shares"] for r in rows); pf=sum(r["pnl"] for r in rows)
print("DRY 结算窗口 %d | 胜 %d (%.0f%%) | 均价 %.3f | 账面EV $%+.1f ROI %+.1f%%\n"%(
    len(rows),w,w/len(rows)*100,statistics.mean(r["avg_px"] for r in rows),pf,pf/cost*100 if cost else 0))
print("=== 按加仓深度 (=走强程度): 这是机制核心 ===")
for lo,hi,l in ((1,2,"只底仓(没走强)"),(2,3,"加1次"),(3,99,"加2-3次(强走强重仓)")):
    g=[r for r in rows if lo<=r["n_fills"]<hi]
    if g:
        gw=sum(1 for r in g if r["won"]); gc=sum(r["avg_px"]*r["shares"] for r in g); gp=sum(r["pnl"] for r in g)
        print("  %-20s n=%-3d 胜%2.0f%% 均价%.3f 账面ROI%+6.1f%%"%(l,len(g),gw/len(g)*100,statistics.mean(r["avg_px"] for r in g),gp/gc*100 if gc else 0))
# regime split: wobble vs clean
print("\n=== wobble(震荡,停加) vs 干净走强 ===")
for nm,sel in (("wobble了",lambda r:r.get("wobble")),("没wobble(干净)",lambda r:not r.get("wobble"))):
    g=[r for r in rows if sel(r)]
    if g:
        gw=sum(1 for r in g if r["won"])
        print("  %-14s n=%-3d 胜%2.0f%% 均价%.3f 均买%d次"%(nm,len(g),gw/len(g)*100,statistics.mean(r["avg_px"] for r in g),statistics.mean(r["n_fills"] for r in g)))
print("\n注: 账面胜负用binance(favorite档可靠). 重点看'加2-3次重仓'的胜率是否逼近~90%(eebde机制核心).")
