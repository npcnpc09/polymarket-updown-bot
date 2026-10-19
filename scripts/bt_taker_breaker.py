"""bt_taker_breaker.py — would a loss-clustering breaker/regime-pause have helped the TAKER?
The taker fires flat 5sh, so the action is PAUSE (skip the entry) when the regime is hot, not downsize.
For each REAL taker fill, compute the rolling-10 loss count of a stream STRICTLY BEFORE its window-start;
if >=K losses -> this taker entry would have been SKIPPED. Compare KEPT vs SKIPPED PnL/win%, and check
held-out (last 40%, contains the 06-17 eth bleed). Test 3 stream choices: taker-own, zmaker-own, combined."""
import json
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(slug):
    try: return int(slug.rsplit("-",1)[1])
    except: return None
# taker fills (the thing we gate)
tk = []
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl", encoding="utf-8") if l.strip()):
    if o.get("kind")=="entry" and o.get("won") is not None:
        w=ws_of(o.get("slug",""))
        if w: tk.append({"ws":w,"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),"coin":o.get("coin")})
# zmaker fills (for combined stream)
zm = []
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None:
        w=ws_of(o.get("slug",""))
        if w: zm.append({"ws":w,"won":bool(o["won"])})
tk.sort(key=lambda x:x["ws"])
comb = sorted([{"ws":x["ws"],"won":x["won"]} for x in tk]+[{"ws":x["ws"],"won":x["won"]} for x in zm], key=lambda x:x["ws"])
tkonly = sorted([{"ws":x["ws"],"won":x["won"]} for x in tk], key=lambda x:x["ws"])
zmonly = sorted([{"ws":x["ws"],"won":x["won"]} for x in zm], key=lambda x:x["ws"])
def roll(stream, ws):
    prior=[f for f in stream if f["ws"]<ws][-10:]
    return sum(1 for f in prior if not f["won"]), len(prior)
def evaluate(stream, K, label, subset=None):
    src = subset if subset is not None else tk
    kept=[]; skipped=[]
    for f in src:
        r,n = roll(stream, f["ws"])
        if n>=10 and r>=K: skipped.append(f)
        else: kept.append(f)
    def stat(s):
        if not s: return (0,0,0.0)
        return (len(s), sum(1 for x in s if x["won"])/len(s)*100, sum(x["pnl"] for x in s))
    kn,kw,kp = stat(kept); sn,sw,sp = stat(skipped)
    base_p = sum(x["pnl"] for x in src)
    print(f"  {label:22s} K={K} | KEEP n={kn:3d} win%={kw:4.0f} PnL=${kp:+7.2f} | SKIP n={sn:3d} win%={sw:4.0f} PnL=${sp:+7.2f} | base=${base_p:+7.2f} -> gated=${kp:+7.2f} (delta {kp-base_p:+.2f})")
print(f"taker fills {len(tk)} | zmaker fills {len(zm)} | combined {len(comb)}")
print(f"taker base: win%={sum(1 for x in tk if x['won'])/len(tk)*100:.1f} PnL=${sum(x['pnl'] for x in tk):+.2f}\n")
print("=== FULL period (pause taker when stream rolling-10 >= K losses) ===")
for K in (2,3):
    evaluate(tkonly, K, "taker-own stream")
    evaluate(zmonly, K, "zmaker-own stream")
    evaluate(comb,   K, "COMBINED stream")
    print()
# held-out: last 40% of taker fills
cut = tk[int(len(tk)*0.6)]["ws"]
ho = [f for f in tk if f["ws"]>=cut]
print(f"=== HELD-OUT (last 40% = {len(ho)} taker fills, ws>={cut}, contains 06-17 bleed) ===")
for K in (2,3):
    evaluate(comb, K, "COMBINED stream", subset=ho)
print("\nDISCIPLINE: a breaker helps the taker ONLY if the SKIPPED set is clearly -EV (win% < ~80 AND PnL<0)")
print("AND gated PnL > base on the HELD-OUT slice (not just in-sample). If SKIP win% ~= KEEP win%, it's pausing")
print("good trades too (the taker bleed may be too brief to catch with a 10-fill lag). Pause != free.")
