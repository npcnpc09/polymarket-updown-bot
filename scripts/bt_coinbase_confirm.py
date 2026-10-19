"""bt_coinbase_confirm.py — coinbase open = PM strike (settlement-aligned); binance is our primary signal but
can LAG/diverge. We log cb_lead (coinbase lead at entry) + cb_agree on every real fill. Does requiring
coinbase to AGREE / be STRONG filter out losses where binance was the laggard outlier? Real taker fills."""
import json
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
rows=[]
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8") if l.strip()):
    if o.get("kind")=="entry" and o.get("won") is not None:
        rows.append({"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),"cb_lead":o.get("cb_lead"),
                     "cb_agree":o.get("cb_agree"),"lead":o.get("lead2") or o.get("lead"),"coin":o.get("coin")})
def rep(s,lab):
    if not s: print(f"  {lab:28s} n=0"); return
    w=sum(1 for r in s if r["won"]); p=sum(r["pnl"] for r in s)
    print(f"  {lab:28s} n={len(s):3d} win%={w/len(s)*100:5.1f} PnL=${p:+7.2f} avg${p/len(s):+.2f}")
n=len(rows); w=sum(1 for r in rows if r["won"])
print(f"taker fills with cb data: {n}, base win% {w/n*100:.1f}, PnL ${sum(r['pnl'] for r in rows):+.2f}\n")
print("=== by coinbase agreement at entry ===")
rep([r for r in rows if r["cb_agree"] is True],"cb_agree=True (cb same side)")
rep([r for r in rows if r["cb_agree"] is False],"cb_agree=False (cb opposes)")
rep([r for r in rows if r["cb_agree"] is None],"cb_agree=None (no cb)")
print("\n=== by coinbase lead strength (|cb_lead|) ===")
hav=[r for r in rows if r["cb_lead"] is not None]
rep([r for r in hav if abs(r["cb_lead"])<5],"|cb_lead|<5 (weak/turning)")
rep([r for r in hav if 5<=abs(r["cb_lead"])<8],"|cb_lead| 5-8")
rep([r for r in hav if abs(r["cb_lead"])>=8],"|cb_lead|>=8 (strong agree)")
print("\n=== binance-vs-coinbase divergence (binance leads, coinbase lags = our signal the outlier) ===")
both=[r for r in hav if r["lead"] is not None and r["cb_agree"] is True]
rep([r for r in both if abs(r["cb_lead"])>=abs(r["lead"])-1],"cb >= binance (cb confirms/leads)")
rep([r for r in both if abs(r["cb_lead"])<abs(r["lead"])-1],"cb << binance (binance outlier)")
print("\n=== candidate gate: require cb_agree AND |cb_lead|>=8 ===")
rep([r for r in rows if r["cb_agree"] is True and r["cb_lead"] is not None and abs(r["cb_lead"])>=8],"GATE cb_agree & |cb|>=8")
rep([r for r in rows if not(r["cb_agree"] is True and r["cb_lead"] is not None and abs(r["cb_lead"])>=8)],"  (the DROPPED set)")
print("\nREAD: a coinbase-confirm gate helps if the DROPPED set (weak/disagreeing cb) is clearly -EV and the")
print("KEPT set's win% rises. cb_agree is logged real -> this is real-data, not reconstruction.")
