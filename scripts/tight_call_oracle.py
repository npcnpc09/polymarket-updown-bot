"""tight_call_oracle.py — how much would reading CHAINLINK directly help? We can't see Chainlink history,
but we CAN measure the ORACLE-AMBIGUOUS ZONE: for each fill, compute binance's OWN window net move
(open->close). When |net| is tiny (tight call), binance/coinbase/Chainlink can disagree = the only zone
where a better oracle read could matter. Categorize our LOSSES:
  - CLEAR REVERSAL: binance net move is BIG and AGAINST our side -> binance agrees we lost. Oracle read useless.
  - ORACLE-AMBIGUOUS (tight): |net| < THRESH -> coin-flip zone where binance!=Chainlink plausibly flips it.
  - BINANCE-AGREED-WIN-BUT-LOST: binance net says we WON but we lost -> a real binance!=Chainlink mismatch.
The actionable read = how many losses (and $) live in the ambiguous zone, and is that zone ~50% (unpredictable)."""
import json, math
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
kl=json.load(open(ROOT+"/data/klines_cache.json"))
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
def close_at(sym,minute):
    d=kl[sym]; return d.get(str(minute)) or d.get(minute)
def load(fn,eng,pred):
    out=[]
    for l in open(ROOT+"/"+fn,encoding="utf-8"):
        if not l.strip(): continue
        try:o=json.loads(l)
        except:continue
        if pred(o):
            s=o.get("slug","")
            try: ws=int(s.rsplit("-",1)[1])
            except: continue
            dur=900 if "-15m-" in s else 300
            out.append({"ws":ws,"dur":dur,"coin":o.get("coin"),"side":o.get("side"),"won":bool(o["won"]),
                        "pnl":float(o.get("pnl",0) or 0)})
    return out
fills=(load("data/multi_window_engine_live.jsonl","zm",lambda o:o.get("filled") is True and o.get("won") is not None)
      +load("data/early_taker_probe.jsonl","tk",lambda o:o.get("kind")=="entry" and o.get("won") is not None)
      +load("data/multi_window_engine_15m_live.jsonl","15m",lambda o:o.get("filled") is True and o.get("won") is not None))
fills=[f for f in fills if f["coin"] in SYM]
THRESH=5.0  # bps; |net move| below this = oracle-ambiguous tight call
done=[]
for f in fills:
    sym=SYM[f["coin"]]; o=close_at(sym,f["ws"]//60); c=close_at(sym,(f["ws"]+f["dur"])//60)
    if not o or not c: continue
    net=math.log(c/o)*1e4  # binance window net move bps
    d=1 if f["side"]=="Up" else -1
    f["net"]=net; f["bin_win"]=(net*d>0); done.append(f)
n=len(done); W=[f for f in done if f["won"]]; L=[f for f in done if not f["won"]]
agree=sum(1 for f in done if f["bin_win"]==f["won"])
print(f"=== {n} fills with binance window net move computed ===")
print(f"  binance-net-sign AGREES with actual outcome: {agree}/{n} = {agree/n*100:.1f}%  (disagreement = oracle/recon mismatch)")
print(f"\n=== LOSSES ({len(L)}) categorized ===")
tight=[f for f in L if abs(f["net"])<THRESH]
binwin_lost=[f for f in L if f["bin_win"] and abs(f["net"])>=THRESH]   # binance clearly said WIN but lost
clear_rev=[f for f in L if (not f["bin_win"]) and abs(f["net"])>=THRESH] # binance clearly said LOSE too
def s(g): return f"{len(g):3d} losses, ${sum(x['pnl'] for x in g):+8.2f}"
print(f"  CLEAR REVERSAL (|net|>={THRESH}bps, binance agrees we lost): {s(clear_rev)}  <- oracle read USELESS")
print(f"  TIGHT/AMBIGUOUS (|net|<{THRESH}bps coin-flip):               {s(tight)}  <- only zone a better oracle MIGHT help")
print(f"  BINANCE-SAID-WIN but LOST (|net|>={THRESH}, real bin!=CL):    {s(binwin_lost)}  <- true binance!=Chainlink flips")
print(f"\n=== tight-call zone win rate (is it a coin-flip we can't predict?) ===")
for lo,hi in [(0,2),(2,5),(5,10),(10,9999)]:
    b=[f for f in done if lo<=abs(f["net"])<hi]
    if b: print(f"  |net| {lo}-{hi}bps: n={len(b):4d} win%={sum(1 for f in b if f['won'])/len(b)*100:5.1f}")
print(f"\nREAD: 'fixable by Chainlink' is at most the TIGHT + BINANCE-SAID-WIN buckets, AND only if a live")
print(f"Chainlink read could disambiguate at ENTRY (it can't predict the post-entry move). If tight-zone")
print(f"win% ~50%, those are irreducible coin-flips; reading Chainlink live doesn't make them predictable.")
