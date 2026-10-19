"""bt_oracle_mismatch.py — how many of our REAL losses are ORACLE MISMATCH (binance, our signal source, ended
OUR way but PM/Chainlink settled against us) vs genuine REVERSAL (binance also reversed -> we'd lose on either
source)? For each real loss: reconstruct binance's OWN settle (close@ws+300 vs open@ws) and compare to our bet
side + the PM 'won' truth. Bucket mismatches by |binance settle margin| (tight <5bps = oracle coin-flip noise;
clear >=5bps = binance clearly disagreed with Chainlink = systematic divergence)."""
import json, math, time, httpx
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
SYM={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT"}
def ws_of(slug):
    try: return int(slug.rsplit("-",1)[1])
    except: return None
srcs=[("data/multi_window_engine_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None),
      ("data/multi_window_engine_15m_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None),
      ("data/multi_window_engine_sol_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None),
      ("data/early_taker_probe.jsonl",lambda o:o.get("kind")=="entry" and o.get("won") is not None)]
fills=[]
for f,keep in srcs:
    dur=900 if "15m" in f else 300
    try:
        for o in (json.loads(l) for l in open(ROOT+"/"+f,encoding="utf-8") if l.strip()):
            if keep(o):
                w=ws_of(o.get("slug",""))
                if w and o.get("coin") in SYM:
                    fills.append({"coin":o["coin"],"ws":w,"dur":dur,"side":o.get("side"),"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0)})
    except FileNotFoundError: pass
# fetch binance 1m opens covering all windows, per coin
def kline_opens(sym,t0,t1):
    M={}; t=t0
    with httpx.Client(timeout=20) as c:
        while t<t1+1000:
            k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":t*1000,"limit":1000}).json()
            if not isinstance(k,list) or not k: break
            for r in k: M[r[0]//1000]=float(r[1])  # minute_ts -> open
            t=k[-1][0]//1000+60
            if len(k)<1000: break
    return M
opens={}
for coin,sym in SYM.items():
    cf=[x for x in fills if x["coin"]==coin]
    if not cf: continue
    t0=min(x["ws"] for x in cf); t1=max(x["ws"]+x["dur"] for x in cf)
    opens[coin]=kline_opens(sym,t0,t1)
def px(coin,ts):  # binance open at minute boundary ts
    M=opens.get(coin,{})
    for d in (0,60,-60,120):
        if ts+d in M: return M[ts+d]
    return None
losses=[x for x in fills if not x["won"]]
rev=mm_tight=mm_clear=0; rev_pnl=mmt_pnl=mmc_pnl=0.0; nopx=0
clear_list=[]
for x in losses:
    o=px(x["coin"],x["ws"]); cl=px(x["coin"],x["ws"]+x["dur"])
    if o is None or cl is None: nopx+=1; continue
    bin_bps=math.log(cl/o)*1e4
    bin_settle="Up" if cl>=o else "Down"
    we_bet=x["side"]
    if bin_settle==we_bet:   # binance ended OUR way but PM said we LOST = oracle mismatch
        if abs(bin_bps)<5: mm_tight+=1; mmt_pnl+=x["pnl"]
        else: mm_clear+=1; mmc_pnl+=x["pnl"]; clear_list.append((x,round(bin_bps,1)))
    else:                    # binance also went against us = genuine reversal
        rev+=1; rev_pnl+=x["pnl"]
tot=rev+mm_tight+mm_clear
print(f"real losses analyzed: {tot} (skipped {nopx} no-price) | total loss $ {rev_pnl+mmt_pnl+mmc_pnl:+.2f}")
print(f"\n=== loss decomposition (binance=our signal, PM/Chainlink=settlement) ===")
print(f"  GENUINE REVERSAL (binance also reversed): {rev:3d} ({rev/tot*100:4.0f}%)  ${rev_pnl:+.2f}")
print(f"  ORACLE MISMATCH - tight <5bps (coin-flip): {mm_tight:3d} ({mm_tight/tot*100:4.0f}%)  ${mmt_pnl:+.2f}")
print(f"  ORACLE MISMATCH - CLEAR >=5bps (binance clearly disagreed): {mm_clear:3d} ({mm_clear/tot*100:4.0f}%)  ${mmc_pnl:+.2f}")
print(f"\nREAD: tight mismatches = irreducible oracle noise on near-coin-flips (expected, small). CLEAR mismatches")
print(f"= binance clearly ended our way but Chainlink settled opposite = the systematic divergence worth fearing.")
if clear_list:
    print(f"\n  CLEAR-mismatch losses (binance settle bps shown — binance said we WIN by this much, PM said LOSE):")
    for x,b in sorted(clear_list,key=lambda t:-abs(t[1]))[:15]:
        from datetime import datetime,timezone
        print(f"    {datetime.fromtimestamp(x['ws'],timezone.utc).strftime('%m-%d %H:%M')} {x['coin']} {x['side']} bin{b:+.0f}bps pnl${x['pnl']:.2f}")
