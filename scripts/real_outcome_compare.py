"""Measure the binance-reconstruction artifact DIRECTLY: for ce25's RESOLVED windows, compare the binance-
reconstructed winner (1m open@st vs close) against gamma's REAL resolved outcome (outcomePrices [1,0]/[0,1]
= Chainlink/UMA settlement). Disagreement rate overall + by price band tells us how much binance inflated
the cheap-longshot edge, and whether his selection needs re-decoding on real outcomes."""
import httpx,math,statistics,time
c=httpx.Client(timeout=20,headers={"User-Agent":"Mozilla/5.0"})
CE="0xcE25E214D5cfE4f459cf67F08DF581885AAE7Fdc"
A=[]
for off in range(0,6000,500):
    try: a=c.get("https://data-api.polymarket.com/activity",params={"user":CE,"limit":500,"offset":off}).json()
    except: break
    if not isinstance(a,list) or not a: break
    A+=[x for x in a if x.get("type")=="TRADE" and (x.get("side") or "").upper()=="BUY"]
    if len(a)<500: break
SYM={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT","xrp":"XRPUSDT","doge":"DOGEUSDT"}; DUR={"5m":300,"15m":900}
now=int(time.time())
# windows that ENDED >2h ago (resolved in gamma), keep ce25's trades grouped by window
byslug={}
for x in A:
    s=x.get("slug","");parts=s.split("-")
    if "updown" not in s or len(parts)<4: continue
    coin=parts[0];dur=next((d for d in DUR if f"-{d}-" in s),None)
    if coin not in SYM or not dur: continue
    try: st=int(parts[-1])
    except: continue
    if st+DUR[dur]>now-7200: continue   # ended >2h ago
    byslug.setdefault(s,{"coin":coin,"dur":dur,"st":st,"trades":[]})["trades"].append({"side":x.get("outcome"),"price":x.get("price") or 0,"size":x.get("size") or 0})
slugs=list(byslug)[:160]
print("已结算>2h的窗口: %d (查gamma真实解析 vs binance重建)\n"%len(slugs))
# binance klines
need=set(byslug[s]["coin"] for s in slugs);KL={}
for coin in need:
    sts=[byslug[s]["st"] for s in slugs if byslug[s]["coin"]==coin]
    out={};cur=min(sts)-120;hi=max(byslug[s]["st"]+DUR[byslug[s]["dur"]] for s in slugs if byslug[s]["coin"]==coin)+300
    while cur<hi:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1m","startTime":cur*1000,"endTime":hi*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[4]))
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    KL[coin]=out
def gamma_winner(slug):
    try:
        m=c.get("https://gamma-api.polymarket.com/markets",params={"slug":slug}).json()
        if not m: return None
        op=m[0].get("outcomePrices"); outs=m[0].get("outcomes")
        if isinstance(op,str): import json as _j; op=_j.loads(op); outs=_j.loads(outs)
        op=[float(v) for v in op]
        if max(op)>=0.99 and min(op)<=0.01:  # resolved
            return outs[op.index(max(op))]
    except: pass
    return None
rows=[]; nres=0; disagree=0
for s in slugs:
    w=byslug[s];o=KL[w["coin"]].get(w["st"]);cl=KL[w["coin"]].get(w["st"]+DUR[w["dur"]])
    if not o or not cl: continue
    bwin="Up" if cl[1]>=o[0] else "Down"
    gwin=gamma_winner(s)
    if gwin is None: continue
    nres+=1
    if bwin!=gwin: disagree+=1
    for t in w["trades"]:
        rows.append({"price":t["price"],"size":t["size"],"bwon":t["side"]==bwin,"gwon":t["side"]==gwin,"agree":bwin==gwin})
print("可比对窗口(gamma已resolved): %d | binance重建与真实结算不一致: %d (%.0f%%)\n"%(nres,disagree,disagree/nres*100 if nres else 0))
print("=== 不一致率 按价格档 (artifact集中在哪) ===")
for lo,hi,l in ((0,0.2,"<0.2"),(0.2,0.35,"0.2-0.35"),(0.35,0.5,"0.35-0.5"),(0.5,0.7,"0.5-0.7"),(0.7,1.01,">=0.7")):
    g=[r for r in rows if lo<=r["price"]<hi]
    if g: print("  %-10s n=%-4d binance与真实不一致 %.0f%%"%(l,len(g),sum(1 for r in g if not r["agree"])/len(g)*100))
print("\n=== 他真实ROI(gamma结算) vs binance重建ROI, 按价格档 ===")
for lo,hi,l in ((0,0.2,"<0.2"),(0.2,0.35,"0.2-0.35"),(0.35,0.5,"0.35-0.5"),(0.5,0.7,"0.5-0.7"),(0.7,1.01,">=0.7")):
    g=[r for r in rows if lo<=r["price"]<hi]
    if not g: continue
    cost=sum(r["size"]*r["price"] for r in g)
    bpf=sum((r["size"]*(1-r["price"]) if r["bwon"] else -r["size"]*r["price"]) for r in g)
    gpf=sum((r["size"]*(1-r["price"]) if r["gwon"] else -r["size"]*r["price"]) for r in g)
    print("  %-10s n=%-4d  binance ROI%+6.1f%%  |  真实ROI%+6.1f%%"%(l,len(g),bpf/cost*100 if cost else 0,gpf/cost*100 if cost else 0))
