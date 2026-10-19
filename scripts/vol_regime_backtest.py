"""Find the BTC volatility band that suits us: bucket historical DRY btc/eth windows by the
contemporaneous BTC realized vol (prior-30min, reconstructed from binance) and show win%/EV per band.
Hypothesis: too-calm = low-quality signals (bad), too-wild = whippy reversals (bad), middle = sweet spot.
This grounds the real-time gauge in data instead of a guessed threshold."""
import json,math,httpx,statistics
ROWS=[]
for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if "won" in r and isinstance(r.get("B"),(int,float)) and r.get("coin")in("btc","eth"):
        ROWS.append(r)
sts=[int(r["slug"].split("-")[-1]) for r in ROWS]
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
# BTC vol drives the whole crypto regime; use BTC vol for ALL windows (btc & eth)
BTC=fetch("BTCUSDT",min(sts)-2000,max(sts)+360)
def vol30(st):
    # stdev of 1-min log returns over prior 30 min, in bps
    px=[BTC.get(st-60*i) for i in range(31)]
    px=[p for p in px if p]
    if len(px)<10: return None
    rets=[math.log(px[i]/px[i+1])*1e4 for i in range(len(px)-1)]
    return statistics.pstdev(rets)
recs=[]
for r in ROWS:
    st=int(r["slug"].split("-")[-1]); v=vol30(st)
    if v is None: continue
    recs.append({"won":r["won"],"B":r["B"],"vol":v})
print("窗口: %d (有BTC vol)\n"%len(recs))
def pnl(r): return 5*(1-r["B"]) if r["won"] else -5*r["B"]
vs=sorted(r["vol"] for r in recs)
# 分位边界
qs=[vs[int(len(vs)*f)] for f in (0.2,0.4,0.6,0.8)]
print("BTC 30min波动率(bps/min)分位: 20%%=%.1f 40%%=%.1f 60%%=%.1f 80%%=%.1f\n"%tuple(qs))
bands=[(-1,qs[0],"最低20% 太平"),(qs[0],qs[1],"20-40%"),(qs[1],qs[2],"40-60% 中"),(qs[2],qs[3],"60-80%"),(qs[3],1e9,"最高20% 太狂")]
print("=== 按BTC波动率分档 ===")
for lo,hi,lbl in bands:
    b=[r for r in recs if lo<r["vol"]<=hi]
    if not b: print("  %-14s n=0"%lbl); continue
    w=sum(1 for r in b if r["won"]); ev=statistics.mean(pnl(r) for r in b)
    print("  %-14s vol(%.1f-%.1f] n=%-4d 胜%2.0f%% EV%+.2f 总$%+.1f"%(lbl,lo if lo>0 else 0,hi if hi<1e9 else 99,len(b),w/len(b)*100,ev,sum(pnl(r) for r in b)))
print("\n基线全部: 胜%.0f%% EV%+.2f"%(sum(1 for r in recs if r["won"])/len(recs)*100,statistics.mean(pnl(r) for r in recs)))
