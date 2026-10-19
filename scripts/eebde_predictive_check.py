"""Key question: is eebde's edge REACTIVE (momentum we already have) or ANTICIPATORY (prediction we
don't)? Split his favorite picks by whether, at his $300-commit moment, the underlying already led his
side (reactive) or not (anticipatory/early). Compare WIN RATE + his conviction $ + price. If anticipatory
wins MORE -> he has genuine direction prediction (the real alpha). If same/less -> purely reactive momentum."""
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
    WT[r["slug"]].append((r.get("timestamp",0),r.get("outcome"),r.get("price",0) or 0,r.get("size",0) or 0))
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
def lead(coin,st,sec):
    d=BN[coin]; o=d.get(st)
    if not o: return None
    p=d.get(st+(sec//60)*60)
    return math.log(p[1]/o[0])*1e4 if p else None
def winner(coin,st):
    d=BN[coin]; o=d.get(st); cl=d.get(st+240) or d.get(st+300)
    return ("Up" if cl[1]>=o[0] else "Down") if (o and cl) else None
groups=defaultdict(list)
for slug,trs in WT.items():
    coin="btc" if slug.startswith("btc") else "eth"; st=int(slug.split("-")[-1])
    w=winner(coin,st)
    if not w: continue
    trs.sort(key=lambda x:x[0]); cum=defaultdict(float); commit=None
    for ts,o,p,sz in trs:
        cum[o]+=p*sz
        if commit is None and cum[max(cum,key=cum.get)]>=300:
            commit=ts-st; break
    if commit is None: continue
    fav=max(cum,key=cum.get); favval=cum[fav]
    lc=lead(coin,st,max(0,min(299,commit)))
    if lc is None: continue
    toward=lc if fav=="Up" else -lc
    typ="预判(标的领反向)" if toward<=-3 else ("反应(标的领同向)" if toward>=3 else "中性")
    groups[typ].append({"win":fav==w,"val":favval,"commit":commit,"toward":toward})
print("eebde favorite 入场类型 vs 最终胜率:\n")
print("%-20s %6s %8s %10s %10s"%("类型","n","favorite胜率","平均$","承诺秒"))
for typ in ("反应(标的领同向)","中性","预判(标的领反向)"):
    g=groups.get(typ,[])
    if not g: continue
    wr=sum(1 for r in g if r["win"])/len(g)*100
    print("%-20s %6d %7.0f%% %10.0f %9.0fs"%(typ,len(g),wr,statistics.mean(r["val"] for r in g),statistics.median(r["commit"] for r in g)))
# 预判型里, 大注的赢率(他高信心预判更准?)
antic=groups.get("预判(标的领反向)",[])
if antic:
    big=[r for r in antic if r["val"]>=1000]
    print("\n预判型里大注(>=$1000): n=%d 胜率%.0f%% (vs 全预判%.0f%%)"%(
        len(big),sum(1 for r in big if r["win"])/len(big)*100 if big else 0,sum(1 for r in antic if r["win"])/len(antic)*100))
