"""Validate eebde's early-favorite-maker edge on REAL settlement. Fetch his recent activity via offset
(dense trader -> ~1-2h, thousands of trades + redeems). Winner per window from his REDEEMs (real). Decode:
is his FAVORITE band (>=0.5) actually +EV on real settlement (vs ce25 whose favorites were breakeven)? And
does he get CHEAP fills (the early-maker advantage)? This answers whether 'z-gated early maker' has a real
edge to chase — using real data, zero of our money."""
import httpx,statistics,datetime
from collections import defaultdict
EE="0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
A=[]
for off in range(0,4000,500):
    try: a=c.get("https://data-api.polymarket.com/activity",params={"user":EE,"limit":500,"offset":off}).json()
    except: break
    if not isinstance(a,list) or not a: break
    A+=a
    if len(a)<500: break
print("拉到 %d 条 (offset封顶)"%len(A))
OUT=["Up","Down"]; DUR={"5m":300,"15m":900}
W={}
for r in A:
    s=r.get("slug","")
    if "updown" not in s: continue
    parts=s.split("-")
    try: st=int(parts[-1])
    except: continue
    w=W.setdefault(s,{"st":st,"buys":[],"ridx":None,"rsize":0.0})
    t=r.get("type")
    if t=="TRADE" and (r.get("side","").upper()=="BUY"):
        w["buys"].append({"oc":r.get("outcome"),"price":r.get("price") or 0,"size":r.get("size") or 0,"ts":r.get("timestamp",st)})
    elif t=="REDEEM":
        w["rsize"]+=r.get("size") or 0
        if r.get("outcomeIndex") is not None: w["ridx"]=r.get("outcomeIndex")
def winner(w):
    if w["ridx"] in (0,1): return OUT[w["ridx"]]
    if w["rsize"]>0:
        up=sum(b["size"] for b in w["buys"] if b["oc"]=="Up"); dn=sum(b["size"] for b in w["buys"] if b["oc"]=="Down")
        return "Up" if abs(w["rsize"]-up)<abs(w["rsize"]-dn) else "Down"
    return None
resolved=[(s,w,winner(w)) for s,w in W.items() if winner(w)]
allbuys=[(b,win) for s,w,win in resolved for b in w["buys"]]
tspan=(max(w["st"] for s,w in W.items())-min(w["st"] for s,w in W.items()))/3600 if W else 0
print("窗口 %d | 可定真实赢家 %d | 已解析BUY %d笔 | 跨~%.1fh\n"%(len(W),len(resolved),len(allbuys),tspan))
# real cash flow
tot_buy=sum(b["price"]*b["size"] for s,w in W.items() for b in w["buys"])
tot_red=sum(w["rsize"] for w in W.values())
print("真实现金流(此样本): 买入$%.0f 赎回$%.0f 净$%+.0f"%(tot_buy,tot_red,tot_red-tot_buy))
def stat(rs,lbl):
    if not rs: print("  %-14s n=0"%lbl);return
    cost=sum(b["price"]*b["size"] for b,w in rs); pf=sum(b["size"]*(1-b["price"]) if b["oc"]==w else -b["size"]*b["price"] for b,w in rs)
    print("  %-14s n=%-5d 真胜%2.0f%% 均价%.3f 真实ROI%+6.1f%%"%(lbl,len(rs),sum(1 for b,w in rs if b["oc"]==w)/len(rs)*100,statistics.mean(b["price"] for b,w in rs),pf/cost*100 if cost else 0))
print("\n=== eebde 真实ROI 按价格档 (真实结算) ===")
for lo,hi,l in ((0,0.3,"<0.3"),(0.3,0.5,"0.3-0.5"),(0.5,0.65,"0.5-0.65fav"),(0.65,0.8,"0.65-0.8fav"),(0.8,1.01,">=0.8fav")):
    stat([(b,win) for b,win in allbuys if lo<=b["price"]<hi],l)
print("\n=== favorite(>=0.5) vs underdog(<0.5) 真实 ===")
stat([(b,win) for b,win in allbuys if b["price"]>=0.5],"favorite>=0.5")
stat([(b,win) for b,win in allbuys if b["price"]<0.5],"underdog<0.5")
# his fill timing within window (early?) on favorites
fav=[(b,win) for b,win in allbuys if b["price"]>=0.5]
offs=[b["ts"]-st for b,win in fav for s,w,wn in resolved if b in w["buys"] for st in [w["st"]]][:0]  # skip heavy
print("\n=== favorite成交价分布 (看他是不是真便宜) ===")
favp=[b["price"] for b,win in fav]
if favp: print("  favorite均价 %.3f | 中位 %.3f | <0.7占比 %.0f%%"%(statistics.mean(favp),statistics.median(favp),sum(1 for p in favp if p<0.7)/len(favp)*100))
print("\n判据: 若favorite真实ROI明显>0 且 成交价便宜(<0.7多) → early-favorite-maker是真边, z-gated值得试")
print("       若favorite≈breakeven(像ce25) → 这个组合没边, 别试")
