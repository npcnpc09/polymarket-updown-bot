"""Decode ce25 on REAL outcomes (a full week). Winner per window = the side he REDEEMED (winning token pays
$1/share, from his REDEEM events) — REAL Chainlink settlement, NOT binance reconstruction. Compute his real
PnL, and his REAL win%/ROI by price band & by side. Finally compare to binance-reconstructed winner to
quantify the artifact. This is the data we lacked."""
import json,os,statistics,math,time
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows=[json.loads(l) for l in open(os.path.join(ROOT,"data","ce25_full.jsonl"),encoding="utf-8")]
DUR={"5m":300,"15m":900}
# group by window
W={}
for r in rows:
    s=r.get("slug","")
    if "updown" not in s: continue
    w=W.setdefault(s,{"buys":[],"redeem_idx":None,"redeem_size":0.0,"sells":[]})
    t=r.get("type")
    if t=="TRADE":
        side=r.get("side","").upper()
        rec={"oc":r.get("outcome"),"price":r.get("price") or 0,"size":r.get("size") or 0}
        if side=="BUY": w["buys"].append(rec)
        elif side=="SELL": w["sells"].append(rec)
    elif t=="REDEEM":
        w["redeem_size"]+=r.get("size") or 0
        oi=r.get("outcomeIndex")
        if oi is not None: w["redeem_idx"]=oi
# winner per window: redeem outcomeIndex (0=Up,1=Down) primary; fallback share-match
OUT=["Up","Down"]
def winner(w):
    if w["redeem_idx"] is not None and w["redeem_idx"] in (0,1): return OUT[w["redeem_idx"]]
    if w["redeem_size"]>0:
        up=sum(b["size"] for b in w["buys"] if b["oc"]=="Up"); dn=sum(b["size"] for b in w["buys"] if b["oc"]=="Down")
        return "Up" if abs(w["redeem_size"]-up)<abs(w["redeem_size"]-dn) else "Down"
    return None
# real outcome per BUY
band_real=lambda lo,hi:[(b["price"],b["size"],b["oc"]==win) for s,w in W.items() if (win:=winner(w)) for b in w["buys"] if lo<=b["price"]<hi]
buys_resolved=[(b["price"],b["size"],b["oc"]==win) for s,w in W.items() if (win:=winner(w)) for b in w["buys"]]
nres=sum(1 for s,w in W.items() if winner(w))
print("窗口 %d | 可定真实赢家(有赎回) %d | 已解析BUY %d笔\n"%(len(W),nres,len(buys_resolved)))
# real PnL over the week (buys cost vs redeems received + sells)
tot_buy=sum(b["price"]*b["size"] for s,w in W.items() for b in w["buys"])
tot_red=sum(w["redeem_size"] for w in W.values())  # winning shares * $1
tot_sell=sum(s2["price"]*s2["size"] for s,w in W.items() for s2 in w["sells"])
print("=== 他这一周真实现金流 (链上) ===")
print("  买入花费 $%.0f | 赎回收到 $%.0f | 卖出收到 $%.0f | 净 $%+.0f"%(tot_buy,tot_red,tot_sell,tot_red+tot_sell-tot_buy))
print("\n=== 真实ROI 按价格档 (真实结算, 非binance) ===")
print("  %-12s %6s %5s %7s"%("价格档","笔","真胜%","真实ROI"))
for lo,hi,l in ((0,0.2,"<0.2"),(0.2,0.3,"0.2-0.3"),(0.3,0.4,"0.3-0.4"),(0.4,0.5,"0.4-0.5"),(0.5,0.65,"0.5-0.65"),(0.65,0.8,"0.65-0.8"),(0.8,1.01,">=0.8")):
    g=band_real(lo,hi)
    if not g: continue
    cost=sum(p*s for p,s,w in g); pf=sum(s*(1-p) if w else -s*p for p,s,w in g)
    wr=sum(1 for p,s,w in g if w)/len(g)*100
    print("  %-12s %6d %4.0f%% %+7.1f%%"%(l,len(g),wr,pf/cost*100 if cost else 0))
print("\n=== favorite(>=0.5) vs underdog(<0.5) 真实 ===")
for nm,lo,hi in (("underdog<0.5",0,0.5),("favorite>=0.5",0.5,1.01)):
    g=band_real(lo,hi); cost=sum(p*s for p,s,w in g); pf=sum(s*(1-p) if w else -s*p for p,s,w in g)
    print("  %-13s n=%-5d 真胜%2.0f%% 真实ROI%+6.1f%% 真实盈亏$%+.0f"%(nm,len(g),sum(1 for p,s,w in g if w)/len(g)*100,pf/cost*100 if cost else 0,pf))
