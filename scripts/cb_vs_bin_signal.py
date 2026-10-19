"""Should we switch the PRIMARY signal from Coinbase to binance? Same windows, same vol, only the LEAD
source differs: Coinbase (engine's recorded lead @~167s) vs binance (reconstructed @165s). For each,
compute z=|lead|/vol, take z>=2.5 entries, compare win%/EV (real settlement). If binance-primary wins
more / is +EV more, switching beats adding a confirmation layer."""
import json,math,httpx,statistics,datetime
ROWS=[]
for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if "won" in r and isinstance(r.get("B"),(int,float)) and r.get("coin")in("btc","eth") and "-5m-" in r.get("slug","") and isinstance(r.get("lead"),(int,float)):
        ROWS.append(r)
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}; sts=[int(r["slug"].split("-")[-1]) for r in ROWS]
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
BN={cn:fetch(SYM[cn],min(sts)-2000,max(sts)+360) for cn in SYM}
def pxat(cn,t):
    lo=(t//60)*60;hi=lo+60;a=BN[cn].get(lo);b=BN[cn].get(hi)
    if a is None:return None
    if b is None:return a
    return a*(1-(t-lo)/60.0)+b*(t-lo)/60.0
def pnl(r): return 5*(1-r["B"]) if r["won"] else -5*r["B"]
recs=[]
for r in ROWS:
    cn=r["coin"];st=int(r["slug"].split("-")[-1])
    cl=[BN[cn].get(st-60*i) for i in range(31)];cl=[x for x in cl if x]
    if len(cl)<20:continue
    vol=statistics.pstdev([math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))])
    if vol<=0:continue
    op=pxat(cn,st);p165=pxat(cn,st+165)
    if op is None or p165 is None:continue
    cb_lead=r["lead"]                      # Coinbase (recorded, signed)
    bin_lead=math.log(p165/op)*1e4         # binance signed
    recs.append({"won":r["won"],"B":r["B"],"cbz":abs(cb_lead)/vol,"binz":abs(bin_lead)/vol,
                 "cb_side":"Up" if cb_lead>=0 else "Down","bin_side":"Up" if bin_lead>=0 else "Down",
                 "eng_side":r["side"],"day":datetime.datetime.utcfromtimestamp(st).strftime("%m-%d")})
def stat(rs,lbl):
    if not rs: print("  %-26s n=0"%lbl); return
    w=sum(1 for r in rs if r["won"]); ev=statistics.mean(pnl(r) for r in rs)
    print("  %-26s n=%-4d 胜%2.0f%% EV%+.2f 总$%+.1f"%(lbl,len(rs),w/len(rs)*100,ev,sum(pnl(r) for r in rs)))
print("样本: %d\n"%len(recs))
print("=== 主信号对比: Coinbase-z>=2.5 vs binance-z>=2.5 (同窗口) ===")
# 注意: won是基于引擎下注的side(=Coinbase side). 对binance-primary, 若binance side不同, 用binance side的胜负
cbwin=lambda r: r["won"]
def binwin(r):
    # 引擎下的是cb_side; 若binance会下bin_side: 同向则同胜负, 反向则相反
    return r["won"] if r["bin_side"]==r["cb_side"] else (not r["won"])
cb=[r for r in recs if r["cbz"]>=2.5]
print("  Coinbase-z>=2.5 (现状):    n=%-4d 胜%2.0f%% EV%+.2f"%(len(cb),sum(1 for r in cb if cbwin(r))/len(cb)*100 if cb else 0,statistics.mean(pnl(r) for r in cb) if cb else 0))
binr=[r for r in recs if r["binz"]>=2.5]
bw=sum(1 for r in binr if binwin(r)); bev=statistics.mean(5*(1-r["B"]) if binwin(r) else -5*r["B"] for r in binr) if binr else 0
print("  binance-z>=2.5 (改用binance): n=%-4d 胜%2.0f%% EV%+.2f"%(len(binr),bw/len(binr)*100 if binr else 0,bev))
# 两者都>=2.5 且同向(纯净的"双确认")
both=[r for r in recs if r["cbz"]>=2.5 and r["binz"]>=2.5 and r["cb_side"]==r["bin_side"]]
print("  两者都>=2.5且同向:          n=%-4d 胜%2.0f%% EV%+.2f"%(len(both),sum(1 for r in both if r["won"])/len(both)*100 if both else 0,statistics.mean(pnl(r) for r in both) if both else 0))
print("\n=== binance-z>=2.5 按天 OOS ===")
for d in sorted(set(r["day"] for r in recs)):
    dd=[r for r in binr if r["day"]==d]
    if dd: print("  %s: n=%-3d 胜%2.0f%% EV%+.2f"%(d,len(dd),sum(1 for r in dd if binwin(r))/len(dd)*100,statistics.mean(5*(1-r["B"]) if binwin(r) else -5*r["B"] for r in dd)))
