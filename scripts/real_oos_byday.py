"""Per-day OOS of ce25's cheap-underdog edge on REAL outcomes (redeem-settled). Split the full week by day;
does the underdog +EV hold EVERY day, or is it a few days? The overfit/stability detector."""
import json,os,datetime
from collections import defaultdict
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows=[json.loads(l) for l in open(os.path.join(ROOT,"data","ce25_full.jsonl"),encoding="utf-8")]
DUR={"5m":300,"15m":900}; OUT=["Up","Down"]
W={}
for r in rows:
    s=r.get("slug","")
    if "updown" not in s: continue
    parts=s.split("-");
    try: st=int(parts[-1])
    except: continue
    w=W.setdefault(s,{"st":st,"buys":[],"ridx":None,"rsize":0.0})
    t=r.get("type")
    if t=="TRADE" and (r.get("side","").upper()=="BUY"):
        w["buys"].append({"oc":r.get("outcome"),"price":r.get("price") or 0,"size":r.get("size") or 0})
    elif t=="REDEEM":
        w["rsize"]+=r.get("size") or 0
        if r.get("outcomeIndex") is not None: w["ridx"]=r.get("outcomeIndex")
def winner(w):
    if w["ridx"] in (0,1): return OUT[w["ridx"]]
    if w["rsize"]>0:
        up=sum(b["size"] for b in w["buys"] if b["oc"]=="Up"); dn=sum(b["size"] for b in w["buys"] if b["oc"]=="Down")
        return "Up" if abs(w["rsize"]-up)<abs(w["rsize"]-dn) else "Down"
    return None
# per-day accumulation
days=defaultdict(lambda:defaultdict(lambda:[0,0,0.0,0.0]))  # day -> band -> [n, wins, cost, pnl]
def bandname(p):
    return "<0.3" if p<0.3 else "0.3-0.4" if p<0.4 else "0.4-0.5" if p<0.5 else "fav>=0.5"
for s,w in W.items():
    win=winner(w)
    if not win: continue
    d=datetime.datetime.utcfromtimestamp(w["st"]).strftime("%m-%d")
    for b in w["buys"]:
        won=(b["oc"]==win); cost=b["price"]*b["size"]; pf=b["size"]*(1-b["price"]) if won else -cost
        cell=days[d][bandname(b["price"])]
        cell[0]+=1; cell[1]+=1 if won else 0; cell[2]+=cost; cell[3]+=pf
print("=== 按天 真实ROI (underdog各档 + favorite), 真实结算 ===\n")
print("%-7s | %-18s | %-18s | %-18s | %-14s"%("日","<0.3","0.3-0.4","0.4-0.5","fav>=0.5"))
print("%-7s | %s"%("","  ".join(["n / 胜% / ROI"]*4 if False else "")))
bands=["<0.3","0.3-0.4","0.4-0.5","fav>=0.5"]
for d in sorted(days):
    cells=[]
    for b in bands:
        n,wn,cost,pf=days[d][b]
        if n: cells.append("%5d %2.0f%% %+5.1f%%"%(n,wn/n*100,pf/cost*100 if cost else 0))
        else: cells.append("    -")
    print("%-7s | %s"%(d," | ".join(cells)))
# 汇总每档: 多少天为正
print("\n=== 稳定性: 每档多少天为正 ===")
for b in bands:
    pos=sum(1 for d in days if days[d][b][0]>0 and days[d][b][3]>0); tot=sum(1 for d in days if days[d][b][0]>0)
    roi_all=sum(days[d][b][3] for d in days)/sum(days[d][b][2] for d in days)*100 if sum(days[d][b][2] for d in days) else 0
    print("  %-10s %d/%d天为正 | 全周ROI%+.1f%%"%(b,pos,tot,roi_all))
