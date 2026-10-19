"""Backtest the MODEL-edge directional strategy on eebde's real trades as the
price oracle (his fills ~ cheap maker prices = the maker CEILING). For each of
his updown trades: compute model p_lead from underlying (Binance klines), his
price, edge; resolution = close vs open from klines. Segment by edge bucket ->
realized WR and EV. Large sample, instant. If +EV at his price -> worth paper.
"""
import json, httpx, math, time, re
from collections import defaultdict
sess=httpx.Client(timeout=25, headers={"User-Agent":"Mozilla/5.0"})
EEBDE="0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
SIGMA=0.5; YR=31557600.0; MARG=0.04
def Phi(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
COINS={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT","xrp":"XRPUSDT","doge":"DOGEUSDT"}

# 1. backfill eebde updown trades
buys=[]; before=None; pg=0
while pg<30:
    p={"user":EEBDE,"limit":500}
    if before: p["end"]=before
    a=sess.get("https://data-api.polymarket.com/activity",params=p).json()
    if not isinstance(a,list) or not a: break
    pg+=1
    for x in a:
        if x.get("type")=="TRADE" and x.get("side")=="BUY":
            sl=x.get("slug","") or ""
            m=re.match(r"(\w+)-updown-(5m|15m)-(\d+)",sl)
            if m and m.group(1) in COINS:
                buys.append((m.group(1),300 if m.group(2)=="5m" else 900,int(m.group(3)),
                             x["timestamp"],x.get("outcome"),float(x.get("price",0)),float(x.get("usdcSize",0))))
    o=min(x["timestamp"] for x in a)
    if before is not None and o>=before: break
    before=o-1
    if len(a)<500: break
print(f"eebde updown trades: {len(buys)}")
if not buys: raise SystemExit
t0=min(b[2] for b in buys)-120; t1=max(b[2]+b[1] for b in buys)+120

# 2. klines per coin -> minute->close
PX={}
for coin,sym in COINS.items():
    px={}; cur=t0*1000; end=t1*1000
    while cur<end:
        kl=sess.get("https://api.binance.com/api/v3/klines",
            params={"symbol":sym,"interval":"1m","startTime":int(cur),"endTime":int(end),"limit":1000}).json()
        if not isinstance(kl,list) or not kl: break
        for k in kl: px[int(k[0]//60000)]=(float(k[1]),float(k[4]))  # (open,close)
        cur=kl[-1][0]+60000
        if len(kl)<1000: break
    PX[coin]=px
    print(f"  {coin}: {len(px)} mins")
def price_at(coin,ts):
    mi=int(ts//60); m=PX[coin]
    for d in range(6):
        if mi-d in m: return m[mi-d][1]   # close of that minute ~ price
    return None
def open_at(coin,ts):
    mi=int(ts//60); m=PX[coin]
    for d in range(6):
        if mi+d in m: return m[mi+d][0]   # OPEN of the window-start minute
    return None

# 3. per trade: model edge + resolution
def bucket(e):
    if e< -0.02: return "<-.02"
    if e<0.02: return "-.02..02"
    if e<0.06: return ".02..06"
    if e<0.12: return ".06..12"
    return ">.12"
seg=defaultdict(lambda:[0,0,0.0,0.0])  # [n,wins,sum_maker_ev, sum_taker_ev] by EDGE
fseg=defaultdict(lambda:[0,0,0.0,0.0]) # by model confidence (fair)
alln=allw=0; used=0
for coin,dur,start,ts,side,price,usd in buys:
    if side not in ("Up","Down"): continue
    op=open_at(coin,start); S=price_at(coin,ts); cl=price_at(coin,start+dur)
    if not op or not S or not cl or price<=0 or price>=1: continue
    ttl=(start+dur)-ts
    if ttl<=0: continue
    v=SIGMA*math.sqrt(ttl/YR)
    p_up=Phi(math.log(S/op)/v) if v>0 else 0.5
    p_his=p_up if side=="Up" else 1-p_up
    edge=p_his-price
    win=(side=="Up" and cl>=op) or (side=="Down" and cl<op)
    alln+=1; allw+=1 if win else 0
    if not (0.30<=price<=0.90): continue    # directional tradeable zone (exclude longshot/near-certain)
    used+=1
    b=bucket(edge)
    tev=(1.0/price-1.0) if win else -1.0          # at his (cheap) price = maker ceiling
    tkr=min(price+0.03,0.99)                        # taker ~ his price + 3c spread estimate
    mev=(1.0/tkr-1.0) if win else -1.0
    seg[b][0]+=1; seg[b][1]+=1 if win else 0; seg[b][2]+=tev; seg[b][3]+=mev
    fb="0.55-0.65" if p_his<0.65 else "0.65-0.75" if p_his<0.75 else "0.75-0.85" if p_his<0.85 else "0.85+"
    if edge>MARG: fseg[fb][0]+=1; fseg[fb][1]+=1 if win else 0; fseg[fb][2]+=tev; fseg[fb][3]+=mev

print(f"\nusable: {used} | overall WR {allw/alln*100:.1f}% (eebde all-trade WR sanity)")
print(f"\n=== by MODEL edge bucket (EV at HIS price=maker ceiling / +3c=taker est) ===")
print(f"{'edge':>10} {'n':>6} {'WR':>6} {'maker_EV':>9} {'taker_EV':>9}")
for b in ["<-.02","-.02..02",".02..06",".06..12",">.12"]:
    if b in seg:
        n,w,mk,tk=seg[b]
        print(f"{b:>10} {n:>6} {w/n*100:>5.1f}% {mk/n*100:>+8.1f}% {tk/n*100:>+8.1f}%")
print(f"\n=== by MODEL CONFIDENCE (fair), edge>{MARG} only — does high-confidence = +EV? ===")
print(f"{'fair':>10} {'n':>6} {'WR':>6} {'maker_EV':>9} {'taker_EV':>9}")
for b in ["0.55-0.65","0.65-0.75","0.75-0.85","0.85+"]:
    if b in fseg:
        n,w,mk,tk=fseg[b]
        print(f"{b:>10} {n:>6} {w/n*100:>5.1f}% {mk/n*100:>+8.1f}% {tk/n*100:>+8.1f}%")
print("\n>>> KEY: if fair>=0.80 (high-confidence) shows high WR + +EV at taker, the refined")
print("strategy (high-confidence only) has real merit. maker_EV=his price; taker=+3c.")
