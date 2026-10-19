"""Final piece: what REAL PM price does the STRENGTHENING lead trade at by ~150s? Decides if 'enter at 150s
on a still-strengthening lead' (94% win) is +EV (cheap) or priced-in (thin). For recent windows: binance 1s
lead path (lead@60 vs lead@150 = strengthening?), winner (binance — reliable, this side is the favorite),
and all-trader BUY price on the lead side at offset 140-165s. ROI at that real price + the 94% win."""
import httpx,math,statistics,time
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
CE="0xcE25E214D5cfE4f459cf67F08DF581885AAE7Fdc"
A=[]
for off in range(0,2500,500):
    try: a=c.get("https://data-api.polymarket.com/activity",params={"user":CE,"limit":500,"offset":off}).json()
    except: break
    if not isinstance(a,list) or not a: break
    A+=[x for x in a if x.get("type")=="TRADE" and x.get("conditionId")]
    if len(a)<500: break
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}; now=int(time.time()); wins={}
for x in A:
    s=x.get("slug","");parts=s.split("-")
    if "updown" not in s or "-5m-" not in s: continue
    coin=parts[0]
    if coin not in SYM: continue
    try: st=int(parts[-1])
    except: continue
    if st+300>now-30: continue
    wins[s]=(x["conditionId"],coin,st)
wins=dict(list(wins.items())[:90])
print("取 %d 个 btc/eth 5m窗口\n"%len(wins))
def lead_path(coin,st):
    try:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1s","startTime":st*1000,"endTime":(st+305)*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: return None
        d={int(x[0]//1000)-st:float(x[4]) for x in k}; op=float(k[0][1]); cl=float(k[-1][4])
        def lat(off):
            ks=[o for o in d if o>=off]
            return math.log(d[min(ks)]/op)*1e4 if ks else None
        return op,cl,lat(60),lat(150)
    except: return None
rows=[]
for slug,(cid,coin,st) in wins.items():
    lp=lead_path(coin,st)
    if not lp: continue
    op,cl,l60,l150=lp
    if l60 is None or l150 is None or abs(l60)<3: continue
    side="Up" if l60>=0 else "Down"; win="Up" if cl>=op else "Down"
    l60s=abs(l60); l150s=l150*(1 if side=="Up" else -1)
    streng = l150s>=l60s and l150s>=8
    # all-trader BUY price on the 150s-side at offset 140-165s
    try: trs=c.get("https://data-api.polymarket.com/trades",params={"market":cid,"limit":1000}).json()
    except: continue
    if not isinstance(trs,list): continue
    px=[t.get("price") for t in trs if (t.get("side") or "").upper()=="BUY" and t.get("outcome")==side and t.get("timestamp") and 140<=t["timestamp"]-st<=165 and t.get("price")]
    if not px: continue
    rows.append({"side":side,"price150":statistics.mean(px),"streng":streng,"won":side==win,"l150":l150s})
print("可分析窗口 %d\n"%len(rows))
def ev(rs,lbl):
    if not rs: print("  %-24s n=0"%lbl);return
    wr=sum(1 for r in rs if r["won"])/len(rs); ap=statistics.mean(r["price150"] for r in rs)
    roi=(wr*(1-ap)-(1-wr)*ap)/ap*100
    print("  %-24s n=%-3d 真胜%2.0f%% 150s真实价%.3f → ROI%+6.1f%%"%(lbl,len(rs),wr*100,ap,roi))
print("=== 走强lead在150s: 真实价 + ROI ===")
ev([r for r in rows if r["streng"]],"走强(>=8且更强)")
ev([r for r in rows if not r["streng"]],"没走强")
ev(rows,"全部150s领先侧")
print("\n=== 走强 × 150s强度档 ===")
for lo,hi,l in ((8,15,"走强 8-15"),(15,25,"走强 15-25"),(25,99,"走强>=25")):
    ev([r for r in rows if r["streng"] and lo<=r["l150"]<hi],l)
print("\n判据: 走强lead在150s真实价 + 94%胜 → ROI明显>0=可做(单发taker); ≈0=priced-in薄")
