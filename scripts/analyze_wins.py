"""What do the WINNING trades teach us? Use real settled trades (early_taker paid / early_maker avg_px + won).
Per-share PnL = (1-price) if won else -price. Bucket by ENTRY PRICE: win%, avg profit PER WIN, net EV/share,
total $ — to find WHERE the winners' money comes from and whether any price cell is net +EV after losers.
Also by ENTRY OFFSET (early=cheaper=more profit/win?). The winners' lesson is economic: cheap wins pay big,
expensive wins are thin; the question is whether a cheap sub-cell nets positive once losses are netted in."""
import json,os
from collections import defaultdict
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T=[]
for fn in ("early_taker_probe.jsonl","early_maker_live.jsonl"):
    fp=os.path.join(ROOT,"data",fn)
    if not os.path.exists(fp): continue
    for l in open(fp,encoding="utf-8"):
        if not l.strip(): continue
        r=json.loads(l)
        if not r.get("live"): continue
        if r.get("kind")=="entry" and "won" in r and r.get("paid"):
            T.append({"price":r["paid"],"won":r["won"],"off":r.get("offset"),"coin":r.get("coin"),"src":"taker"})
        elif "n_W" in r and (r.get("winner") or r.get("win")) and r.get("avg_px"):
            T.append({"price":r["avg_px"],"won":r["n_W"]>r["n_L"],"off":None,"coin":r.get("coin"),"src":"maker"})
print("赢/输总单 %d (赢%d 输%d)\n"%(len(T),sum(1 for t in T if t["won"]),sum(1 for t in T if not t["won"])))
def stat(rs):
    if not rs: return None
    w=[t for t in rs if t["won"]]; ev=sum((1-t["price"]) if t["won"] else -t["price"] for t in rs)/len(rs)
    profwin=sum(1-t["price"] for t in w)/len(w) if w else 0
    losslose=sum(t["price"] for t in rs if not t["won"])/max(1,len(rs)-len(w))
    return len(rs),len(w)/len(rs)*100,profwin,losslose,ev
print("=== 按入场价分桶 (净EV/股 = 赢单赚 vs 输单亏 的真实净额) ===")
print("%-12s %5s %6s %9s %9s %9s"%("价格档","n","胜%","赢均赚/股","输均亏/股","净EV/股"))
BANDS=[(0,0.6),(0.6,0.7),(0.7,0.8),(0.8,0.86),(0.86,1.01)]
for lo,hi in BANDS:
    s=stat([t for t in T if lo<=t["price"]<hi])
    if s: print("%.2f-%-.2f    %5d %5.0f%% %+8.3f %+8.3f \033[1m%+8.3f\033[0m"%(lo,hi,s[0],s[1],s[2],-s[3],s[4]))
print("\n=== 按入场时点 (taker, 越早越便宜?) ===")
tk=[t for t in T if t["src"]=="taker" and t["off"] is not None]
for lo,hi,lab in ((0,60,"<60s"),(60,120,"60-120s"),(120,300,"120-300s")):
    g=[t for t in tk if lo<=t["off"]<hi]; s=stat(g)
    if s:
        ap=sum(t["price"] for t in g)/len(g)
        print("  %-9s n=%-3d 胜%2.0f%% 均价%.3f 净EV/股%+.3f"%(lab,s[0],s[1],ap,s[4]))
print("\n总结要回答: (1)赢单的钱主要来自哪个价档(便宜档赢均赚大); (2)有没有哪个价档净EV>0(赢盖过输);")
print("(3)早入场是否=更便宜+不更差. 若最便宜档净EV最高/转正 => 那是该聚焦的赢单画像.")
