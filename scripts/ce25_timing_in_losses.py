"""For OUR losing live windows: pull ce25's per-trade SEQUENCE (offset, side, price, size) and answer the
key question — at OUR entry moment, was ce25 ALREADY on the opposite (winning) side (=he had an early
indicator we lack = foresight), or was he on OUR side early and only averaged to the other side LATER
(=no secret signal, just continuous-averaging follow = hindsight)? This decides whether the hybrid needs a
missing signal or is purely mechanical add-as-confirmed."""
import json,os,httpx,statistics
from collections import defaultdict
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows=[json.loads(l) for l in open(os.path.join(ROOT,"data","early_taker_probe.jsonl"),encoding="utf-8")]
live=[r for r in rows if r.get("live") and r.get("won") is not None]
losses=[r for r in live if not r["won"]]
DUR={"5m":300,"15m":900}
def st_of(slug):
    try: return int(slug.split("-")[-1])
    except: return None
CE="0xcE25E214D5cfE4f459cf67F08DF581885AAE7Fdc"
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
A=[]
for off in range(0,5000,500):
    try: a=c.get("https://data-api.polymarket.com/activity",params={"user":CE,"limit":500,"offset":off}).json()
    except: break
    if not isinstance(a,list) or not a: break
    A+=[x for x in a if x.get("type")=="TRADE" and (x.get("side") or "").upper()=="BUY"]
    if len(a)<500: break
bySlug=defaultdict(list)
for x in A:
    if x.get("slug"): bySlug[x["slug"]].append(x)
def netside_upto(trades,cutoff_ts):
    val=defaultdict(float)
    for x in trades:
        if x.get("timestamp",0)<=cutoff_ts: val[x.get("outcome")]+=(x.get("price") or 0)*(x.get("size") or 0)
    if not val: return None,0,0
    s=max(val,key=val.get); return s,val.get("Up",0),val.get("Down",0)
print("=== 我们输单窗口里 ce25 的时序 (关键: 我们入场时他在哪侧) ===\n")
early_foresight=0; late_avg=0; checked=0
for r in sorted(losses,key=lambda x:x["slug"]):
    slug=r["slug"]; st=st_of(slug); trs=bySlug.get(slug,[])
    our_ts=st+r["offset"]; our_side=r["side"]
    if not trs:
        print("%-26s 我们%s@%ds 输 | ce25 不在场\n"%(slug,our_side,r["offset"])); continue
    checked+=1
    seq=sorted(trs,key=lambda x:x.get("timestamp",0))
    first=seq[0]; foff=first.get("timestamp",st)-st
    # ce25 net side AT our entry moment, and at end
    side_at_entry,_,_=netside_upto(seq,our_ts)
    side_final,vu,vd=netside_upto(seq,st+DUR["5m"]+60)
    winner=r["winner"]
    verdict=""
    if side_at_entry and side_at_entry!=our_side: verdict="★他入场时已在对面(foresight)"; early_foresight+=1
    elif side_at_entry==our_side: verdict="他入场时跟我们同侧→后续averaging才挪"; late_avg+=1
    print("%-26s 我们%-4s@%3ds (赢家%s)"%(slug,our_side,r["offset"],winner))
    print("   ce25首单 @%3ds %s@%.3f | 我们入场时他净在: %s | 终值侧: %s(Up$%.0f/Down$%.0f)"%(
        foff,first.get("outcome"),first.get("price") or 0,side_at_entry,side_final,vu,vd))
    print("   逐笔: "+" ".join("%ds%s%.2f"%(x.get("timestamp",st)-st,(x.get("outcome") or "?")[0],x.get("price") or 0) for x in seq[:14]))
    print("   >>> %s\n"%verdict)
print("=== 小结 ===")
print("输单中可查 %d 个: ce25入场时已在对面(他有早信号) %d | 入场时同侧后averaging挪 %d"%(checked,early_foresight,late_avg))
