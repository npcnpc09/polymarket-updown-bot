"""Recompute OUR early-taker's REAL win rate (using ce25's redeems as ground-truth winner per window, since
ce25 traded ~every window — REAL settlement, not binance). Then check eebde's winning cell: lead-aligned
(lead>=5) + favorite (paid>=0.5) + early (offset<90). Did WE really win ~90% there (=> capturable), or
~72% (=> it's eebde's selection)?"""
import json,os,statistics
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT=["Up","Down"]
# real winner per window from ce25's redeems
realwin={}
for l in open(os.path.join(ROOT,"data","ce25_full.jsonl"),encoding="utf-8"):
    r=json.loads(l); s=r.get("slug","")
    if "updown" not in s: continue
    w=realwin.setdefault(s,{"buys":[],"ridx":None,"rsize":0.0})
    if r.get("type")=="TRADE" and r.get("side","").upper()=="BUY": w["buys"].append((r.get("outcome"),r.get("size") or 0))
    elif r.get("type")=="REDEEM":
        w["rsize"]+=r.get("size") or 0
        if r.get("outcomeIndex") is not None: w["ridx"]=r.get("outcomeIndex")
def winner(s):
    w=realwin.get(s)
    if not w: return None
    if w["ridx"] in (0,1): return OUT[w["ridx"]]
    if w["rsize"]>0:
        up=sum(sz for oc,sz in w["buys"] if oc=="Up"); dn=sum(sz for oc,sz in w["buys"] if oc=="Down")
        return "Up" if abs(w["rsize"]-up)<abs(w["rsize"]-dn) else "Down"
    return None
# our early-taker trades
ours=[json.loads(l) for l in open(os.path.join(ROOT,"data","early_taker_probe.jsonl"),encoding="utf-8")]
ours=[r for r in ours if r.get("live") and r.get("side") and r.get("paid") and r.get("lead") is not None]
matched=[]; nomatch=0
for r in ours:
    rw=winner(r["slug"])
    if rw is None: nomatch+=1; continue
    r["real_won"]=(r["side"]==rw); matched.append(r)
print("我们early-taker live单 %d | 能用ce25真实结算判的 %d (其余%d窗ce25没覆盖)\n"%(len(ours),len(matched),nomatch))
# binance vs real disagreement
dis=sum(1 for r in matched if r.get("won")!=r["real_won"])
print("binance判的胜负 与 真实结算 不一致: %d/%d = %.0f%%\n"%(dis,len(matched),dis/len(matched)*100 if matched else 0))
def stat(rs,lbl):
    if not rs: print("  %-26s n=0"%lbl);return
    wr=sum(1 for r in rs if r["real_won"])/len(rs)
    cost=sum(r["paid"] for r in rs); pf=sum((1-r["paid"]) if r["real_won"] else -r["paid"] for r in rs)
    bwr=sum(1 for r in rs if r.get("won"))/len(rs)
    print("  %-26s n=%-3d 真胜%2.0f%%(binance说%2.0f%%) 均价%.3f 真实ROI%+6.1f%%"%(lbl,len(rs),wr*100,bwr*100,statistics.mean(r["paid"] for r in rs),pf/cost*100 if cost else 0))
print("=== 我们early-taker 真实表现(用ce25结算) ===")
stat(matched,"全部")
print("\n=== eebde的cell: 顺势(lead>=5) + favorite(paid>=0.5) + 早入 ===")
stat([r for r in matched if r["lead"]>=5 and r["paid"]>=0.5],"顺势favorite (任意时点)")
stat([r for r in matched if r["lead"]>=5 and r["paid"]>=0.5 and r["offset"]<90],"顺势favorite 早入<90s")
stat([r for r in matched if r["lead"]>=5 and r["paid"]>=0.5 and r["offset"]>=90],"顺势favorite 晚入>=90s")
print("\n=== 对比: 不顺势 / 便宜side ===")
stat([r for r in matched if r["lead"]<5],"lead<5 (弱/逆势)")
stat([r for r in matched if r["paid"]<0.5],"便宜side(paid<0.5)")
