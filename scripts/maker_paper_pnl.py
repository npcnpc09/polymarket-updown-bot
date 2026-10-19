"""PAPER PnL of the confirmed-strengthening maker probe (passive_maker.jsonl), IF it had been real money at
SHARES/fill. PnL per filled probe = SHARES*((1-bid) if won else -bid). HEAVY CAVEAT: passive=front-of-queue=
OVERestimates fills; proven this session to overstate ~0.27/sh vs real fills. This is an optimistic upper
bound, NOT a promise. Real number needs live orders."""
import json,os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows=[json.loads(l) for l in open(os.path.join(ROOT,"data","passive_maker.jsonl"),encoding="utf-8") if l.strip()]
SHARES=5
nwin=len(set(r["slug"] for r in rows))
print("confirmed-strengthening maker probe: %d 独立窗, %d 探测点\n"%(nwin,len(set((r['slug'],r['cp']) for r in rows))))
print("假设 %d股/单, 各折扣档的纸面累计PnL (passive=乐观上限):\n"%SHARES)
print("%-8s %6s %7s %7s %10s %10s"%("档","成交数","胜%","均价","纸面PnL$","每窗$"))
from collections import defaultdict
byt=defaultdict(list)
for r in rows: byt[r["tier"]].append(r)
for d in (0.0,0.02,0.04,0.06):
    g=byt.get(d,[])
    fl=[r for r in g if r["filled"]]
    if not fl: continue
    w=sum(1 for r in fl if r["won"])
    pnl=sum(SHARES*((1-r["bid"]) if r["won"] else -r["bid"]) for r in fl)
    ap=sum(r["bid"] for r in fl)/len(fl)
    print("mid-%-3dc %6d %6.0f%% %6.3f %+9.2f %+9.2f"%(int(d*100),len(fl),w/len(fl)*100,ap,pnl,pnl/nwin))
print("\n冷水: passive成交率是上限(真挂单填得少); 已证纸面高估~0.27/股; n=%d窗小."%nwin)
print("真钱实际会明显低于这个数, 可能仍正(深档)也可能被fill逆选吃成负 -- 只有live能定.")
