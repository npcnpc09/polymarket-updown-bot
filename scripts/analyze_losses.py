"""Why did our DIRECTION picks lose? For every settled real trade (early_taker + early_maker), the bought side
= the lead side. Fetch binance 1s lead path, characterize each window relative to the bought side:
  entry_lead  = lead toward bought side at ~45s (was the signal strong or marginal at entry?)
  peak_toward = max lead toward bought side over window (did conviction ever build?)
  final       = lead toward bought side at settle (did it end our way?)
  REVERSED    = peak_toward>=8 but final<0 (strong lead then flipped = the reversal tail)
  WEAK        = peak_toward<8 (never had conviction = marginal entry, noise)
  TIGHT       = |final|<5 bps (near coin-flip at settle = binance-vs-Chainlink oracle risk)
Compare LOSERS vs WINNERS on these to find the dominant failure mode of our direction selection."""
import json,os,math
import httpx
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
c=httpx.Client(timeout=20,headers={"User-Agent":"Mozilla/5.0"})
# collect settled trades: (coin, st, bought_side, won) from both bots
trades={}
def add(slug,won,bought):
    p=slug.split("-"); coin=p[0]
    if coin not in SYM: return
    try: st=int(p[-1])
    except: return
    trades[(coin,st,slug)]=(bought,won)
for fn in ("early_taker_probe.jsonl","early_maker_live.jsonl"):
    fp=os.path.join(ROOT,"data",fn)
    if not os.path.exists(fp): continue
    for l in open(fp,encoding="utf-8"):
        if not l.strip(): continue
        r=json.loads(l)
        if not r.get("live"): continue
        win=r.get("winner") or r.get("win")
        if r.get("kind")=="entry" and "won" in r:  # taker
            won=r["won"]; bought=r.get("side")
        elif "n_W" in r:  # maker settle
            if win is None: continue
            won=r["n_W"]>r["n_L"]; bought=win if won else ("Up" if win=="Down" else "Down")
        else: continue
        if win is None and bought is None: continue
        add(r["slug"],won,bought)
def path(coin,st):
    try:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":SYM[coin],"interval":"1s","startTime":st*1000,"endTime":(st+300)*1000,"limit":320}).json()
        if not isinstance(k,list) or len(k)<60: return None
        op=float(k[0][1]); return [(int(x[0]//1000)-st,math.log(float(x[4])/op)*1e4) for x in k]
    except: return None
def lead_at(pth,off):
    cand=[l for o,l in pth if o>=off]; return cand[0] if cand else None
def feats(pth,bought):
    sgn=1 if bought=="Up" else -1
    el=lead_at(pth,45); el=el*sgn if el is not None else 0
    tw=[l*sgn for _,l in pth]; peak=max(tw); final=tw[-1]
    return el,peak,final
rows=[]
for (coin,st,slug),(bought,won) in trades.items():
    if not bought: continue
    pth=path(coin,st)
    if not pth: continue
    el,peak,final=feats(pth,bought)
    rows.append({"won":won,"entry":el,"peak":peak,"final":final,
                 "reversed":peak>=8 and final<0,"weak":peak<8,"tight":abs(final)<5})
W=[r for r in rows if r["won"]]; L=[r for r in rows if not r["won"]]
def avg(rs,k): return sum(r[k] for r in rs)/len(rs) if rs else 0
def pct(rs,k): return sum(1 for r in rs if r[k])/len(rs)*100 if rs else 0
print("重建 %d 窗 (赢%d / 输%d)\n"%(len(rows),len(W),len(L)))
print("%-8s %6s %7s %7s %7s %8s %8s %8s"%("","n","入场lead","峰值lead","终值lead","反转%","弱信号%","tight%"))
print("%-8s %6d %+7.1f %+7.1f %+7.1f %7.0f%% %7.0f%% %7.0f%%"%("赢窗",len(W),avg(W,"entry"),avg(W,"peak"),avg(W,"final"),pct(W,"reversed"),pct(W,"weak"),pct(W,"tight")))
print("%-8s %6d %+7.1f %+7.1f %+7.1f %7.0f%% %7.0f%% %7.0f%%"%("输窗",len(L),avg(L,"entry"),avg(L,"peak"),avg(L,"final"),pct(L,"reversed"),pct(L,"weak"),pct(L,"tight")))
# decompose losers
rev=[r for r in L if r["reversed"]]; weak=[r for r in L if r["weak"]]; tight=[r for r in L if r["tight"]]
print("\n=== 输窗失败归因 (n=%d) ==="%len(L))
print("  反转(强lead>=8后翻盘):   %2d 窗 (%.0f%%)"%(len(rev),pct(L,"reversed")))
print("  弱信号(峰值从未到8):     %2d 窗 (%.0f%%)"%(len(weak),pct(L,"weak")))
print("  tight(终值|lead|<5, 接近平/可能Chainlink翻): %2d 窗 (%.0f%%)"%(len(tight),pct(L,"tight")))
print("\n判读: 输窗入场lead vs 赢窗入场lead 差多少=信号选择有没有问题; 反转%高=不可消的尾部;")
print("弱信号%高=入场门槛太松(可提lead门槛); tight%高=oracle噪音(binance!=Chainlink, 非方向错).")
