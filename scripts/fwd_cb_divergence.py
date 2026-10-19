"""fwd_cb_divergence.py — FORWARD validation of the coinbase-divergence signal.
Hypothesis (in-sample + time-split OOS, 2026-06-18): when binance (our primary) OUTRUNS coinbase (cb<<binance),
trades are -EV; when coinbase confirms/leads (cb>=binance), trades are +EV. coinbase open == PM strike, so
cb-confirm = settlement-aligned. NO trade change deployed — this just splits fills by a fixed cutoff into
IN-SAMPLE (<=cutoff, what motivated the hypothesis) vs FORWARD (>cutoff, the clean out-of-sample test).
Re-run over the coming days; the signal is real ONLY if it HOLDS forward (confirm > outlier) on the >cutoff set.
cb_lead / lead2 / cb_agree are already logged live -> no instrumentation needed, data accrues automatically."""
import json
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
CUTOFF = 1781797107   # forward-test start: 2026-06-18 ~ set when hypothesis formed (in-sample baseline = 546 fills before)
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
rows=[]
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8") if l.strip()):
    if o.get("kind")=="entry" and o.get("won") is not None:
        w=ws_of(o.get("slug","")); bl=o.get("lead2") or o.get("lead")
        if w and o.get("cb_lead") is not None and bl:
            rows.append({"ws":w,"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),
                         "cb":abs(o["cb_lead"]),"bl":abs(bl),"agree":o.get("cb_agree")})
def confirm(r): return r["agree"] is True and r["cb"]>=r["bl"]-1
def rep(s,lab):
    if not s: print(f"    {lab:32s} n=0"); return
    w=sum(1 for r in s if r["won"]); p=sum(r["pnl"] for r in s)
    print(f"    {lab:32s} n={len(s):3d} win%={w/len(s)*100:5.1f} PnL=${p:+7.2f}")
ins=[r for r in rows if r["ws"]<=CUTOFF]; fwd=[r for r in rows if r["ws"]>CUTOFF]
for name,sub in (("IN-SAMPLE (<=cutoff, motivated hypothesis)",ins),("FORWARD (>cutoff, OUT-OF-SAMPLE TEST)",fwd)):
    print(f"=== {name}: {len(sub)} fills ===")
    rep([r for r in sub if confirm(r)],"cb>=binance (confirm)")
    rep([r for r in sub if not confirm(r)],"cb<<binance (outlier)")
print(f"\nForward fills so far: {len(fwd)}. Need ~80-120 before the forward split is meaningful.")
print("VERDICT RULE: deploy a cb-confirm gate ONLY if FORWARD confirm-set beats outlier-set by a similar")
print("margin (~+6-12pp win, outlier clearly -EV). If it vanishes/flips forward -> in-sample artifact, drop it.")
