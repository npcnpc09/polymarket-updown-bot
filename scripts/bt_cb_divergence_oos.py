"""bt_cb_divergence_oos.py — time-split OOS check on the coinbase-divergence signal (cb>=binance = confirm
vs cb<<binance = our signal the outlier). In-sample it was 86%/+$64.50 vs 80.4%/-$14.08. Does it HOLD on a
held-out time slice (last 40%)? That's the discipline gate before any deploy."""
import json
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
rows=[]
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8") if l.strip()):
    if o.get("kind")=="entry" and o.get("won") is not None:
        w=ws_of(o.get("slug",""))
        bl=o.get("lead2") or o.get("lead")
        if w and o.get("cb_lead") is not None and bl:
            rows.append({"ws":w,"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),
                         "cb":abs(o["cb_lead"]),"bl":abs(bl),"agree":o.get("cb_agree")})
rows.sort(key=lambda x:x["ws"])
cut=rows[int(len(rows)*0.6)]["ws"]
def rep(s,lab):
    if not s: print(f"  {lab:34s} n=0"); return
    w=sum(1 for r in s if r["won"]); p=sum(r["pnl"] for r in s)
    print(f"  {lab:34s} n={len(s):3d} win%={w/len(s)*100:5.1f} PnL=${p:+7.2f}")
def confirm(r): return r["agree"] is True and r["cb"]>=r["bl"]-1
for name,sub in (("TRAIN (first 60%)",[r for r in rows if r["ws"]<cut]),
                 ("HELD-OUT (last 40%)",[r for r in rows if r["ws"]>=cut])):
    print(f"=== {name} ===")
    rep([r for r in sub if confirm(r)],"cb>=binance (confirm = KEEP)")
    rep([r for r in sub if not confirm(r)],"cb<<binance/disagree (DROP)")
print("\nHOLDS if the held-out KEEP set still beats the DROP set (confirm > outlier) by a similar margin.")
