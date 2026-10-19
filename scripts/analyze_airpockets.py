"""analyze_airpockets.py — fingerprint the 20sh cell LOSSES (air-pockets) vs cell WINNERS.
n is tiny (watch-only, NOT a filter). Pull every feature for each loss + the winner distribution to
see what (if anything) the losses share: side, price, lead/maxlead/z/vol, persist/flips/sharp_flip, coin,
time-of-day. Settle direction (tight call?) reconstructed where possible."""
import json, time, statistics as st
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
rows = [json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()]
cell = [r for r in rows if r.get("filled") and r.get("pnl") is not None and r.get("sh") == 20]
loss = [r for r in cell if r.get("won") is False]
win = [r for r in cell if r.get("won") is True]
print(f"cell: {len(cell)} fills | {len(win)} win / {len(loss)} loss\n")

FEATS = ["lead", "max_lead", "zscore", "vol30", "persist", "accel", "flips", "since_flip", "old_side_peak", "flip_swing"]
def fnum(r, k):
    v = r.get(k)
    return v if isinstance(v, (int, float)) else None

print("=== THE 3 LOSSES (full features) ===")
for r in loss:
    ws = int(r["slug"].split("-")[-1]); hh = time.strftime("%H:%M", time.gmtime(ws))
    print(f"  {r['coin']} {r['side']} B={r['B']} z={r.get('zscore')} vol30={r.get('vol30')} lead={r.get('lead')} "
          f"maxlead={r.get('max_lead')} persist={r.get('persist')} flips={r.get('flips')} sharp={r.get('sharp_flip')} "
          f"accel={r.get('accel')} @ {hh}UTC")

print("\n=== LOSS vs WIN distribution (median [min..max]) ===")
def dist(rows, k):
    vals = [fnum(r, k) for r in rows if fnum(r, k) is not None]
    if not vals: return "n/a"
    return f"{st.median(vals):.2f} [{min(vals):.1f}..{max(vals):.1f}]"
print(f"  {'feature':12s} {'LOSS(n=%d)'%len(loss):28s} {'WIN(n=%d)'%len(win):28s}")
for k in FEATS:
    print(f"  {k:12s} {dist(loss,k):28s} {dist(win,k):28s}")

print("\n=== categorical splits ===")
for k in ("side", "coin"):
    lc = {}; wc = {}
    for r in loss: lc[r.get(k)] = lc.get(r.get(k), 0)+1
    for r in win: wc[r.get(k)] = wc.get(r.get(k), 0)+1
    print(f"  {k}: LOSS {lc}  |  WIN {wc}")
# price band
def band(r): return "0.90-0.92" if r["B"] < 0.92 else ("0.92-0.94" if r["B"] < 0.94 else "0.94-0.95")
lb = {}; wb = {}
for r in loss: lb[band(r)] = lb.get(band(r), 0)+1
for r in win: wb[band(r)] = wb.get(band(r), 0)+1
print(f"  B-band: LOSS {lb}  |  WIN {wb}")

# is the LOSS rate higher in any cell sub-bucket? (winrate by feature bucket)
print("\n=== cell win-rate by bucket (does any bucket concentrate losses?) ===")
def wr_by(pred, label):
    sub = [r for r in cell if pred(r)]
    if not sub: return
    w = sum(1 for r in sub if r.get("won")); print(f"  {label:22s} n={len(sub):2d} win%={w/len(sub)*100:5.1f}")
wr_by(lambda r: r["side"] == "Down", "side=Down")
wr_by(lambda r: r["side"] == "Up", "side=Up")
wr_by(lambda r: fnum(r, "vol30") is not None and fnum(r, "vol30") < 4, "vol30<4 (calm)")
wr_by(lambda r: fnum(r, "vol30") is not None and fnum(r, "vol30") >= 4, "vol30>=4")
wr_by(lambda r: fnum(r, "max_lead") is not None and fnum(r, "max_lead") < 12, "maxlead<12 (weak)")
wr_by(lambda r: fnum(r, "max_lead") is not None and fnum(r, "max_lead") >= 12, "maxlead>=12")
wr_by(lambda r: fnum(r, "persist") is not None and fnum(r, "persist") < 0.7, "persist<0.7 (retraced)")
wr_by(lambda r: fnum(r, "persist") is not None and fnum(r, "persist") >= 0.7, "persist>=0.7")
