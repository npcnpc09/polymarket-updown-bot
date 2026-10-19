import json,os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
p=os.path.join(ROOT,"data","strength_maker_live.jsonl")
rows=[json.loads(l) for l in open(p,encoding="utf-8") if l.strip()] if os.path.exists(p) else []
filled=[r for r in rows if not r.get("missed")]
missed=[r for r in rows if r.get("missed")]
print("real FILLED %d, MISSED %d (fill rate %.0f%%)"%(len(filled),len(missed),len(filled)/max(1,len(filled)+len(missed))*100))
for r in filled:
    print("  %s %s @%.2f winner=%s %s pnl=%+.2f"%(r["slug"][-13:],r["side"],r["price"],r.get("winner"),"WON" if r.get("won") else "LOST",r.get("pnl",0)))
if filled:
    w=sum(1 for r in filled if r.get("won")); pnl=sum(r.get("pnl",0) for r in filled)
    print("=> fill win %d/%d=%.0f%%, real PnL $%+.2f, avg px %.3f"%(w,len(filled),w/len(filled)*100,pnl,sum(r["price"] for r in filled)/len(filled)))
