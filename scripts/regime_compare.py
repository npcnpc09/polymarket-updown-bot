"""regime_compare.py — answer: how do the last 2 days' BTC regime differ from prior days, and would the
LOOSE engine-gate (DRY, no agent macro-filter) have made money the last 2 days? Distinguishes
'market had no opportunity' vs 'my resume-gate was too strict'.
(A) binance btc/eth per-UTC-day: net% + avg 1m-vol + ER (trend efficiency).
(B) DRY alt_exec_dry (5m, btc/eth only) per-UTC-day paper PnL — the loose engine self-gate."""
import json, urllib.request, statistics as st
from collections import defaultdict
from datetime import datetime, timezone
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
# (A) binance per-day
def klines(sym):
    u="https://api.binance.com/api/v3/klines?symbol={}&interval=1h&limit=168".format(sym)  # 7 days
    return [(int(k[0]//1000),float(k[1]),float(k[4])) for k in json.load(urllib.request.urlopen(u,timeout=15))]
print("=== (A) binance per-UTC-day: open->close net%, ER(trend eff), hours ===")
for sym in ("BTCUSDT","ETHUSDT"):
    k=klines(sym); byd=defaultdict(list)
    for t,o,c in k: byd[datetime.fromtimestamp(t,tz=timezone.utc).strftime("%m-%d")].append((o,c))
    print("  "+sym)
    for d in sorted(byd):
        rows=byd[d]; o0=rows[0][0]; cl=rows[-1][1]
        closes=[r[1] for r in rows]
        net=abs(closes[-1]-closes[0]); path=sum(abs(closes[i]-closes[i-1]) for i in range(1,len(closes))) if len(closes)>1 else 0
        er=net/path if path else 0
        chg=(cl/o0-1)*100
        print("    {}  net={:+5.2f}%  ER={:.3f}  hrs={}".format(d,chg,er,len(rows)))
# (B) DRY per-day, 5m btc/eth
print("\n=== (B) DRY 5m btc/eth per-UTC-day paper (loose engine self-gate, no agent filter) ===")
def f(x): return float(x or 0)
byd=defaultdict(list)
for l in open(ROOT+"/data/alt_exec_dry.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    try:o=json.loads(l)
    except:continue
    if o.get("won") is None or o.get("ts") is None: continue
    coin=o.get("slug","").split("-")[0]
    if coin not in ("btc","eth"): continue
    byd[datetime.fromtimestamp(o["ts"],tz=timezone.utc).strftime("%m-%d")].append(o)
print("  day     n  win%  taker$  maker$")
for d in sorted(byd):
    s=byd[d]; w=sum(1 for r in s if r.get("won"))
    tk=sum(f(r.get("taker_pnl")) for r in s); mk=sum(f(r.get("maker_pnl")) for r in s if r.get("maker_filled"))
    print("  {}  {:3d}  {:4.0f}  {:+6.2f}  {:+6.2f}".format(d,len(s),w/len(s)*100,tk,mk))
print("\nREAD: if last-2-days ER is much lower (chop) AND DRY paper went flat/negative, then 30h flat is MARKET (no opportunity),")
print("not the strict gate. If DRY paper was clearly +, the strict gate cost us — and loosening is warranted.")
