"""Smart DRY test of the queue-position hypothesis on EXISTING confirmed-strengthening passive data. Each filled
probe has bid + minask (how low the ask went). fill DEPTH = bid - minask: a BRIEF TOUCH (small depth) is what
a FRONT-of-queue (fast) order fills on; a DEEP SWEEP (large depth) is what a BACK-of-queue (slow) order needs.
If brief-touch fills WIN (favorite held, small pullback continued) but deep-sweep fills LOSE (reversal), then
queue position IS the key variable -> our 1ms-to-edge speed advantage gets us the winning touch-fills, and the
strength_maker 25% was just back-of-queue/deep. Tests it on data we already have."""
import json,os
from collections import defaultdict
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# use the archived confirmed-strengthening run
cands=["passive_maker_strengthening.jsonl","passive_maker.jsonl"]
rows=[]
for fn in cands:
    p=os.path.join(ROOT,"data",fn)
    if os.path.exists(p): rows=[json.loads(l) for l in open(p,encoding="utf-8") if l.strip()]; print("using",fn); break
filled=[r for r in rows if r.get("filled") and "bid" in r and "minask" in r]
print("confirmed-strengthening filled probe-tiers: %d\n"%len(filled))
# fill depth = bid - minask (how far past the bid price went)
print("=== 按成交深度分桶 (front-of-queue填浅, back-of-queue填深) ===")
print("%-22s %6s %7s %9s"%("成交深度(bid-minask)","n","胜%","解读"))
buckets=[(-0.001,0.015,"浅触(front-of-queue独享)"),(0.015,0.035,"中"),(0.035,0.08,"深扫(back-of-queue)"),(0.08,9,"很深")]
for lo,hi,lab in buckets:
    g=[r for r in filled if lo<=(r["bid"]-r["minask"])<hi]
    if not g: continue
    w=sum(1 for r in g if r["won"])
    print("%-22s %6d %5.0f%%  %s"%("%.0f-%.0fc"%(lo*100 if lo>0 else 0,hi*100),len(g),w/len(g)*100,lab))
print("\n判读: 若浅触胜% >> 深扫胜% => 队列位置是关键变量, 快手(front-of-queue)拿到高胜的浅触fill,")
print("strength_maker的25%是因为它挂深(mid-4c)只填到深扫=反转. 浅档+快=可能逃逆选.")
print("若浅触也低 => 即便front-of-queue也逆选, 那才是真封闭.")
