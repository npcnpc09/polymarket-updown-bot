"""Gate 2: can a TAKER actually capture the cheap-underdog edge? ce25's real ROI uses HIS fills. We pay the
ASK. Sample LIVE updown order books, find cheap-underdog sides (0.3-0.5), measure bid/ask SPREAD and what a
taker pays. Then apply: at the band's real win-rate, does +EV survive paying the ask? (real win rates from
real_decode_week: 0.3-0.4->38%, 0.4-0.5->47%, <0.3->~18%)."""
import httpx,json,time,statistics
c=httpx.Client(timeout=12,headers={"User-Agent":"Mozilla/5.0"})
COINS={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT","xrp":"XRPUSDT","doge":"DOGEUSDT"}
GAMMA="https://gamma-api.polymarket.com/markets"
WINRATE={"<0.3":0.18,"0.3-0.4":0.38,"0.4-0.5":0.47}  # REAL win rates by band (from ce25 redeem decode)
def toks(slug):
    try:
        a=c.get(GAMMA,params={"slug":slug}).json()
        if a: ids=json.loads(a[0]["clobTokenIds"]); outs=json.loads(a[0]["outcomes"]); return dict(zip(outs,ids))
    except: pass
    return None
def book(tok):
    try:
        b=c.get("https://clob.polymarket.com/book",params={"token_id":tok}).json()
        bids=sorted((float(x["price"]) for x in b.get("bids",[]) if float(x["size"])>0),reverse=True)
        asks=sorted(float(x["price"]) for x in b.get("asks",[]) if float(x["size"])>0)
        return (bids[0] if bids else None),(asks[0] if asks else None)
    except: return None,None
now=int(time.time()); samples=[]
for rounds in range(3):  # sample a few current windows
    ws=(now//300)*300
    for coin in COINS:
        slug=f"{coin}-updown-5m-{ws}"
        tk=toks(slug)
        if not tk: continue
        for oc,tid in tk.items():
            bid,ask=book(tid)
            if bid and ask and 0.25<=ask<=0.55:  # a cheap-ish side
                mid=(bid+ask)/2; samples.append({"coin":coin,"oc":oc,"bid":bid,"ask":ask,"mid":mid,"spread":ask-bid})
    now-=300; time.sleep(0.3)
print("采样到的便宜side(0.25-0.55) %d个\n"%len(samples))
if samples:
    print("=== 真实盘口 spread (便宜side) ===")
    print("  均spread %.1fc | 中位 %.1fc | 均bid %.3f 均ask %.3f"%(statistics.mean(s["spread"] for s in samples)*100,statistics.median(s["spread"] for s in samples)*100,statistics.mean(s["bid"] for s in samples),statistics.mean(s["ask"] for s in samples)))
    for s in samples[:12]:
        print("  %s %-4s bid%.3f ask%.3f spread%.1fc"%(s["coin"],s["oc"],s["bid"],s["ask"],s["spread"]*100))
print("\n=== 边还剩多少: taker付ask vs ce25在mid, 按真实胜率 ===")
def ev(price,wr): return (wr*(1-price)-(1-wr)*price)/price*100  # ROI per $ at this entry price
for b,(lo,hi) in (("0.3-0.4",(0.3,0.4)),("0.4-0.5",(0.4,0.5))):
    g=[s for s in samples if lo<=s["mid"]<hi] or [s for s in samples if lo<=s["ask"]<hi]
    if not g: print("  %s: 本次没采到, 用典型值"%b);
    wr=WINRATE[b]
    mid=statistics.mean(s["mid"] for s in g) if g else (lo+hi)/2
    ask=statistics.mean(s["ask"] for s in g) if g else (lo+hi)/2+0.015
    print("  %-8s 真胜%.0f%% | 在mid%.3f: ROI%+.1f%% | taker付ask%.3f: ROI%+.1f%% (spread吃掉%.1fpp)"%(b,wr*100,mid,ev(mid,wr),ask,ev(ask,wr),ev(mid,wr)-ev(ask,wr)))
print("\n判据: taker付ask后ROI仍明显>0 → 边吃得到; 若被spread吃到≈0 → 只有maker能做(我们maker又adverse)")
