"""REALISTIC backtest of the early_taker filter — model real execution as closely as the data allows:
 - SIGNAL/timing from the cached binance 1s lead path: cross = first |lead|>=8 (off in [5,180]); CONFIRM = lead
   still >=8 same side 15s later (skip faded spikes, exactly like the live bot).
 - PRICE = real all-trader BUY trade on the leading side near the cross (BUY trade = a taker lifting the ask =
   the realistic taker price), + measured SLIPPAGE +1c (live slip_c mean 0.6c, median 1c). If no buy trade near
   the cross -> NO FILL (models liquidity, like our live misses).
 - OUTCOME = real redeem winner (Chainlink), from the cache. Hold to settle.
 - cap 0.85, one trade/window. Then CROSS-VALIDATE: compare to our 37 REAL live taker fills (ground truth)."""
import json,os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cache=json.load(open(os.path.join(ROOT,"data","lead_paths.json")))          # coin|st -> {win, lead:{off:bps}}
fills=json.load(open(os.path.join(ROOT,"data","alltrader_fills_real.json"))) # buy trades: slug,price,won,lead,off
SLIP=0.01; CAP=0.85; LEAD=8; CONFIRM=15; OFFLO=5; OFFHI=180
byslug={}
for f in fills: byslug.setdefault(f["slug"],[]).append(f)
def pathlead(path,off):
    for o in range(off,off+6):
        if str(o) in path: return path[str(o)]
    return None
picks=[]; nocross=0; faded=0; noliq=0
for key,v in cache.items():
    coin,st=key.split("|"); st=int(st); slug="%s-updown-5m-%s"%(coin,st)
    path=v["lead"]; win=v["win"]
    # cross
    cross=None
    for off in range(OFFLO,OFFHI+1,2):
        l=pathlead(path,off)
        if l is not None and abs(l)>=LEAD: cross=(off,l); break
    if not cross: nocross+=1; continue
    coff,cl=cross; side="Up" if cl>0 else "Down"; sgn=1 if cl>0 else -1
    # confirm 15s later
    l2=pathlead(path,coff+CONFIRM)
    if l2 is None or l2*sgn<LEAD: faded+=1; continue
    # realistic price: a BUY trade on the leading side (fill lead>0 toward bought side) near the cross, <CAP
    cands=[f for f in byslug.get(slug,[]) if f["lead"]>0 and coff<=f["off"]<=coff+30 and f["price"]<CAP]
    if not cands: noliq+=1; continue
    cands.sort(key=lambda x:x["off"]); paid=min(cands[0]["price"]+SLIP,0.99)
    won=(side==win)
    picks.append({"paid":paid,"won":won,"side":side,"off":coff})
def rep(name,ps):
    if not ps: print("%s: (空)"%name); return
    n=len(ps); w=sum(1 for p in ps if p["won"]); ev=sum((1-p["paid"]) if p["won"] else -p["paid"] for p in ps)/n
    ap=sum(p["paid"] for p in ps)/n
    print("%-22s n=%-4d 胜%.0f%% 均paid%.3f 净EV/股 %+.3f 总PnL(5股)$%+.1f"%(name,n,w/n*100,ap,ev,ev*5*n))
print("可模拟窗 %d | 无越过%d 信号faded%d 无流动性(取不到价)%d\n"%(len(cache),nocross,faded,noliq))
print("=== 真实化回测 (lead路径越过+确认, 全市场BUY价+1c滑点, 真赎回, cap0.85) ===")
rep("realistic filter",picks)
# cross-validate vs our 37 real live fills
ours=[json.loads(l) for l in open(os.path.join(ROOT,"data","early_taker_probe.jsonl"),encoding="utf-8") if l.strip()]
ours=[{"paid":r["paid"],"won":r["won"]} for r in ours if r.get("kind")=="entry" and r.get("live") and r.get("paid") is not None and "won" in r]
print("\n=== 交叉验证: 我们37笔真实live taker (ground truth) ===")
rep("our real fills",ours)
print("\n判读: 若'真实化回测'净EV ~= '我们真实fills'的水平/方向 => 回测可信; 若回测远高于真实fills => 仍乐观.")
print("注: 我们37笔多来自chop段(偏负); 真实化回测跨数天(含趋势). 两者差异=regime + 残留乐观.")
