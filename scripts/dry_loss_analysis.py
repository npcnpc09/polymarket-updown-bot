"""Analyze recent DRY losing windows: compare W vs L on every recorded label to find separators (or
confirm there are none = losses are the irreducible priced-in tail). Descriptive, NOT a mined filter."""
import json,time,statistics
WIN=int(__import__("sys").argv[1])*3600 if len(__import__("sys").argv)>1 else 10800  # default last 3h
now=int(time.time()); cut=now-WIN
R=[]
for l in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    l=l.strip()
    if not l: continue
    try: r=json.loads(l)
    except: continue
    if "won" not in r or not isinstance(r.get("B"),(int,float)): continue
    try: st=int(r["slug"].split("-")[-1])
    except: continue
    if st>=cut: R.append(r)
def num(rs,k):
    v=[r[k] for r in rs if isinstance(r.get(k),(int,float))]
    return (statistics.mean(v) if v else 0),len(v)
def cmp(rs,lbl):
    W=[r for r in rs if r["won"]]; L=[r for r in rs if not r["won"]]
    if not rs: print("  %s n=0"%lbl); return
    print("\n=== %s  (W%d / L%d, %.0f%%胜) ==="%(lbl,len(W),len(L),len(W)/len(rs)*100))
    for k in ("lead","max_lead","accel","persist","B","cushion","net1h"):
        mw,_=num(W,k); ml,_=num(L,k)
        print("   %-10s 赢均%+7.2f  输均%+7.2f  差%+.2f"%(k,mw,ml,mw-ml))
    # |lead| (abs)
    aw=statistics.mean([abs(r["lead"]) for r in W if isinstance(r.get("lead"),(int,float))]) if W else 0
    al=statistics.mean([abs(r["lead"]) for r in L if isinstance(r.get("lead"),(int,float))]) if L else 0
    print("   %-10s 赢均%+7.2f  输均%+7.2f  差%+.2f"%("|lead|",aw,al,aw-al))
    # eeb_aligned rate
    ew=[r for r in W if r.get("eeb_aligned") is not None]; el=[r for r in L if r.get("eeb_aligned") is not None]
    if ew or el:
        rw=sum(1 for r in ew if r["eeb_aligned"])/len(ew)*100 if ew else 0
        rl=sum(1 for r in el if r["eeb_aligned"])/len(el)*100 if el else 0
        print("   eeb对齐率   赢%.0f%%(n%d)  输%.0f%%(n%d)"%(rw,len(ew),rl,len(el)))
print("近%dh DRY: %d窗"%(WIN//3600,len(R)))
cmp(R,"全部(5币)")
be=[r for r in R if r.get("coin")in("btc","eth")]
cmp(be,"btc/eth")
filt=[r for r in be if (r.get("max_lead")or 0)>=15 and abs(r.get("lead",0)or 0)>=8]
cmp(filt,"btc/eth 自营过滤")
# 列出 btc/eth 过滤后的亏损单
print("\n=== btc/eth 过滤后的亏损单逐个 ===")
for r in sorted([r for r in filt if not r["won"]],key=lambda x:x["slug"]):
    print("  %s %s lead=%+.0f maxL=%.0f accel=%s persist=%s B=%.2f eebAlign=%s"%(
        r["slug"][-13:],r["side"],r.get("lead",0),r.get("max_lead",0),
        r.get("accel"),r.get("persist"),r.get("B",0),r.get("eeb_aligned")))
