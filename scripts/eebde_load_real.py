"""Real-data test of eebde_scale_reverse's core claim: do HEAVY (continuous-averaged) positions win ~97% on
REAL settlement (redeems), and what's the real ROI by how heavily he loaded? If heavy-load windows win ~97%
real -> the continuous-averaging mechanism is REAL (not just paper price-model). Gives real return-per-$."""
import httpx,statistics
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
OUT=["Up","Down"]
W={}
for r in A:
    s=r.get("slug","")
    if "updown" not in s: continue
    w=W.setdefault(s,{"buys":[],"ridx":None,"rsize":0.0})
    if r.get("type")=="TRADE" and r.get("side","").upper()=="BUY":
        w["buys"].append({"oc":r.get("outcome"),"price":r.get("price") or 0,"size":r.get("size") or 0})
    elif r.get("type")=="REDEEM":
        w["rsize"]+=r.get("size") or 0
        if r.get("outcomeIndex") is not None: w["ridx"]=r.get("outcomeIndex")
def winner(w):
    if w["ridx"] in (0,1): return OUT[w["ridx"]]
    if w["rsize"]>0:
        up=sum(b["size"] for b in w["buys"] if b["oc"]=="Up"); dn=sum(b["size"] for b in w["buys"] if b["oc"]=="Down")
        return "Up" if abs(w["rsize"]-up)<abs(w["rsize"]-dn) else "Down"
    return None
# per window: his CONVICTION side (most $ value), its load, did it win (real), window real PnL
wins=[]
for s,w in W.items():
    win=winner(w)
    if not win: continue
    val=defaultdict(float)
    for b in w["buys"]: val[b["oc"]]+=b["price"]*b["size"]
    if not val: continue
    convside=max(val,key=val.get); load=val[convside]
    # real pnl for the whole window (all his buys): redeem - cost
    cost=sum(b["price"]*b["size"] for b in w["buys"]); pf=w["rsize"]-cost
    wins.append({"conv":convside,"load":load,"conv_won":convside==win,"cost":cost,"pnl":pf})
print("可定真实赢家的窗口 %d个 (eebde, ~%dh)\n"%(len(wins),2))
print("=== 按他在窗口投入的总额(连续averaging深度) → 真实胜率 + 真实ROI ===")
print("  %-14s %5s %8s %8s %8s"%("窗口load档","窗数","重仓侧真胜%","该档投入$","真实ROI%"))
bands=[(0,50,"<$50轻"),(50,150,"$50-150"),(150,400,"$150-400"),(400,1000,"$400-1000"),(1000,1e9,">=$1000重")]
for lo,hi,l in bands:
    g=[w for w in wins if lo<=w["load"]<hi]
    if not g: continue
    cw=sum(1 for w in g if w["conv_won"])/len(g)*100
    cost=sum(w["cost"] for w in g); pf=sum(w["pnl"] for w in g)
    print("  %-14s %5d %9.0f%% %8.0f %+8.1f"%(l,len(g),cw,cost,pf/cost*100 if cost else 0))
tot_cost=sum(w["cost"] for w in wins); tot_pf=sum(w["pnl"] for w in wins)
print("\n  全样本: %d窗 投入$%.0f 真实净$%+.0f 真实ROI%+.1f%%"%(len(wins),tot_cost,tot_pf,tot_pf/tot_cost*100 if tot_cost else 0))
print("\n判据: 若load越重→真实胜率越高(逼近90%+) → 连续averaging载持续者机制\033[0m 真实成立(非纸面).")
print("注: ~2h样本, 可能含losing patch; 趋势看机制, 绝对ROI别当周回报.")
