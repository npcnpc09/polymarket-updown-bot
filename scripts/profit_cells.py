"""Where is the PROFIT? ce25's REAL fills (real price+size+outcome) joined to the 600-window cache's REAL
winners (win OR lose known -> UNBIASED, no model, no binance-longshot inflation). EV per trade = size*((1-px)
if won else -px). Bucket by PRICE band -> real ROI per band = where his money actually came from. THEN the
replication test: within each band, is win% > price (the BAND itself is +EV, anyone buying it profits) or does
he need SELECTION (raw band ~breakeven, only his picks win)? Band-edge = replicable; selection-edge = not."""
import json,os,statistics
from collections import defaultdict
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYM={"btc","eth"}; OUT=["Up","Down"]
cache=json.load(open(os.path.join(ROOT,"data","lead_paths.json")))
WIN={k:v["win"] for k,v in cache.items()}   # "coin|st" -> "Up"/"Down"
# his trades in those windows
trades=defaultdict(list)
for l in open(os.path.join(ROOT,"data","ce25_full.jsonl"),encoding="utf-8"):
    r=json.loads(l)
    if r.get("type")!="TRADE" or r.get("side","").upper()!="BUY": continue
    s=r.get("slug","");
    if "-5m-" not in s: continue
    parts=s.split("-"); coin=parts[0]
    if coin not in SYM: continue
    try: st=int(parts[-1])
    except: continue
    key="%s|%d"%(coin,st)
    if key not in WIN: continue
    trades[key].append((r.get("outcome"),float(r.get("price") or 0),float(r.get("size") or 0)))
nt=sum(len(v) for v in trades.values())
print("他在缓存600窗内的真实买单: %d 笔, 跨 %d 窗 (无偏真实结算)\n"%(nt,len(trades)))
BANDS=[(0,0.1),(0.1,0.2),(0.2,0.3),(0.3,0.4),(0.4,0.5),(0.5,0.6),(0.6,0.7),(0.7,0.8),(0.8,0.9),(0.9,1.01)]
agg={b:{"n":0,"sz":0.0,"cost":0.0,"pnl":0.0,"win":0,"pxs":[]} for b in BANDS}
for key,buys in trades.items():
    win=WIN[key]
    for outcome,px,sz in buys:
        if sz<=0 or not (0<px<1): continue
        won=(outcome==win)
        for b in BANDS:
            if b[0]<=px<b[1]:
                a=agg[b]; a["n"]+=1; a["sz"]+=sz; a["cost"]+=px*sz
                a["pnl"]+= sz*((1-px) if won else -px); a["win"]+=1 if won else 0; a["pxs"].append(px); break
print("%-10s %6s %8s %7s %7s %9s %9s"%("价格档","笔数","总股","均价","胜%","真实ROI","盈亏(单位)"))
tot_cost=tot_pnl=0
for b in BANDS:
    a=agg[b]
    if a["n"]==0: continue
    roi=a["pnl"]/a["cost"]*100 if a["cost"] else 0; tot_cost+=a["cost"]; tot_pnl+=a["pnl"]
    avg=statistics.mean(a["pxs"]); wp=a["win"]/a["n"]*100
    # replication: band +EV iff win% > avg price (buying the band blind profits)
    edge=wp-avg*100
    flag="档+EV" if edge>1.5 else ("选择" if edge<-1.5 else "≈持平")
    print("%4.1f-%-4.1f %6d %8.0f %6.3f %6.0f%% %+7.1f%% %+8.1f  win%%-价=%+4.0fpp %s"%(b[0],b[1],a["n"],a["sz"],avg,wp,roi,a["pnl"],edge,flag))
print("\n合计 真实ROI %+.1f%% (盈亏%+.1f / 投入%.1f)"%(tot_pnl/tot_cost*100 if tot_cost else 0,tot_pnl,tot_cost))
print("\n判读: '真实ROI'=他这档真赚多少 (真价×真结算, 无偏). 'win%-价'>0 = 该档\033[1m盲买就+EV\033[0m(可复制,")
print("favorite-longshot偏差); <0 = 他靠\033[1m选择\033[0m赚(我们要复制他的选股, 难). 找 ROI高且'档+EV'的格子.")
