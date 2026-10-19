"""bt_confidence_score.py — can a multi-feature CONFIDENCE score separate winning cell trades from
air-pockets, OUT OF SAMPLE? If yes -> size by score (full=20sh, low=5sh). If no -> entry features can't,
and the only working confidence axis is REGIME (the breaker).
Method: z-maker live fills, features [lead,max_lead,persist,accel,zscore,vol30,B] + REGIME [roll10].
Train (early 60%): standardize, weight each feature by its train correlation-with-WIN. Test (40%):
win-rate by score tercile. A real score => top tercile win% >> bottom on TEST. Compares entry-only vs +regime."""
import json, re, math, statistics as st
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
rows = []
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None and o.get("pnl") is not None:
        m = re.search(r"-5m-(\d+)", o.get("slug", ""))
        if not m: continue
        rows.append({"ws": int(m.group(1)), "won": 1 if o["won"] else 0,
                     "lead": abs(o.get("lead") or 0), "max_lead": o.get("max_lead") or 0,
                     "persist": o.get("persist") or 1, "accel": abs(o.get("accel") or 0),
                     "z": o.get("zscore") or 0, "vol": o.get("vol30") or 0, "B": o.get("B") or 0})
rows.sort(key=lambda r: r["ws"])
for i, r in enumerate(rows): r["roll10"] = sum(1 for x in rows[max(0, i-10):i] if x["won"] == 0)
FEATS = ["lead", "max_lead", "persist", "accel", "z", "vol", "B"]
n = len(rows); cut = int(n*0.6); TR, TE = rows[:cut], rows[cut:]
print(f"{n} z-maker fills | train {len(TR)} ({sum(1-r['won'] for r in TR)} loss) | test {len(TE)} ({sum(1-r['won'] for r in TE)} loss)")

# standardize on train
mu = {f: st.mean([r[f] for r in TR]) for f in FEATS+["roll10"]}
sd = {f: (st.pstdev([r[f] for r in TR]) or 1) for f in FEATS+["roll10"]}
def z(r, f): return (r[f]-mu[f])/sd[f]
# train correlation of each feature with WIN (sign = direction of confidence)
print("\n=== train: correlation of each feature with WIN (which way does 'confidence' go?) ===")
w = {}
for f in FEATS+["roll10"]:
    xs = [z(r, f) for r in TR]; ys = [r["won"] for r in TR]
    mx = st.mean(xs); my = st.mean(ys)
    cov = sum((xs[i]-mx)*(ys[i]-my) for i in range(len(xs)))/len(xs)
    cor = cov/((st.pstdev(xs) or 1)*(st.pstdev(ys) or 1))
    w[f] = cor
    print(f"  {f:9s} corr_with_win={cor:+.3f}")

def score(r, feats): return sum(w[f]*z(r, f) for f in feats)
def tercile_winrate(feats, label):
    scored = sorted(TE, key=lambda r: score(r, feats)); k = len(scored)//3
    bot, top = scored[:k], scored[-k:]
    bw = sum(r["won"] for r in bot)/len(bot)*100; tw = sum(r["won"] for r in top)/len(top)*100
    print(f"  {label:28s} TEST bottom-tercile win%={bw:5.1f}  top-tercile win%={tw:5.1f}  spread={tw-bw:+5.1f}pp")

print("\n=== OOS test: win% by confidence-score tercile (top=high confidence) ===")
tercile_winrate(FEATS, "ENTRY features only")
tercile_winrate(FEATS+["roll10"], "ENTRY + REGIME(roll10)")
tercile_winrate(["roll10"], "REGIME(roll10) ALONE")
tercile_winrate(["vol"], "vol ALONE")
print("\nREAD: spread>0 & robust => that score separates OOS -> usable for sizing. If ENTRY-only spread ~0")
print("but REGIME spread>0 -> confidence must be REGIME-based (the breaker), not entry-signal-based.")
