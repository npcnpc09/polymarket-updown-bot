"""Does the BROADER BTC trend (beyond the 5m window) predict whether a within-window lead persists (win) or
reverses (lose)? Hypothesis: a 5m lead ALIGNED with the larger BTC trend persists; one COUNTER to it gets
mean-reverted (= the 66% reversal losses). For every settled real trade (bought side = 5m lead side), compute
the macro trend BEFORE the window opened: BTC return over prior 30m & 60m, and the coin's OWN prior-30m return.
Bucket win rate by alignment (bought side vs macro direction). If aligned wins >> counter, the macro trend is a
filter that cuts reversals -> only take 5m leads agreeing with the bigger BTC trend."""
import json,os,math
import httpx
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
trades={}
for fn in ("early_taker_probe.jsonl","early_maker_live.jsonl"):
    fp=os.path.join(ROOT,"data",fn)
    if not os.path.exists(fp): continue
    for l in open(fp,encoding="utf-8"):
        if not l.strip(): continue
        r=json.loads(l)
        if not r.get("live"): continue
        win=r.get("winner") or r.get("win"); p=r["slug"].split("-"); coin=p[0]
        if coin not in SYM: continue
        try: st=int(p[-1])
        except: continue
        if r.get("kind")=="entry" and "won" in r: won=r["won"]; bought=r.get("side")
        elif "n_W" in r and win: won=r["n_W"]>r["n_L"]; bought=win if won else ("Up" if win=="Down" else "Down")
        else: continue
        if bought: trades[(coin,st,r["slug"])]=(bought,won)
sts=[st for (_,st,_) in trades]; lo=min(sts)-4000; hi=max(sts)+400
KL={}
for coin,sym in SYM.items():
    out={}; cur=lo
    while cur<hi:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=float(x[4])
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    KL[coin]=out
def close_at(coin,t):
    d=KL[coin]; t=(t//60)*60
    for tt in (t,t-60,t+60):
        if tt in d: return d[tt]
    return None
def macro(coin,st,mins):
    a=close_at(coin,st-mins*60); b=close_at(coin,st)
    return math.log(b/a)*1e4 if a and b else None
rows=[]
for (coin,st,slug),(bought,won) in trades.items():
    bd=1 if bought=="Up" else -1
    m=macro("btc",st,30); m60=macro("btc",st,60); ms=macro(coin,st,30)
    if m is None or ms is None: continue
    rows.append({"won":won,"bd":bd,"btc30":m,"btc60":m60 or 0,"self30":ms,
                 "al_btc30":(m*bd>0),"al_btc60":((m60 or 0)*bd>0),"al_self":(ms*bd>0)})
def wr(rs): return (sum(1 for r in rs if r["won"])/len(rs)*100, len(rs)) if rs else (0,0)
print("可用 %d 窗\n"%len(rows))
print("整体胜率: %.0f%% (n=%d)\n"%wr(rows))
for key,lab in (("al_btc30","BTC前30m趋势"),("al_btc60","BTC前60m趋势"),("al_self","该币自身前30m")):
    al=[r for r in rows if r[key]]; ct=[r for r in rows if not r[key]]
    awr,an=wr(al); cwr,cn=wr(ct)
    print("=== 对齐 %s ==="%lab)
    print("  顺势(下注同向): 胜率 \033[1m%2.0f%%\033[0m (n=%d)"%(awr,an))
    print("  逆势(下注反向): 胜率 \033[1m%2.0f%%\033[0m (n=%d)  差 %+.0fpp"%(cwr,cn,awr-cwr))
# strong macro only
print("\n=== 只看 BTC 前30m 趋势 强(|btc30|>=20bps) ===")
strong=[r for r in rows if abs(r["btc30"])>=20]
al=[r for r in strong if r["al_btc30"]]; ct=[r for r in strong if not r["al_btc30"]]
awr,an=wr(al); cwr,cn=wr(ct)
print("  强趋势顺势: 胜率 %2.0f%% (n=%d)"%(awr,an))
print("  强趋势逆势: 胜率 %2.0f%% (n=%d)  差 %+.0fpp"%(cwr,cn,awr-cwr))
print("\n判读: 顺势胜率 >> 逆势 => BTC大趋势能预测反转 => '只下顺大趋势的5m单'砍掉部分66%反转(有戏).")
print("差不多 => 反转和大趋势无关, 5m内是独立的, 大趋势没用. (n小, 看方向+留意过拟合)")
