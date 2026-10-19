"""dump_losses.py — pull EVERY losing fill (z-maker + taker + sol maker) with all params, write CSV,
print grouped tables + winner-baseline ranges for side-by-side comparison."""
import json, csv, statistics as st
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ld(f):
    out = []
    try:
        for l in open(f, encoding="utf-8"):
            l = l.strip()
            if l:
                try: out.append(json.loads(l))
                except: pass
    except: pass
    return out
def hourof(slug):
    import re
    m = re.search(r"-(5m|15m)-(\d+)", slug)
    if not m: return None, None
    ws = int(m.group(2)); dt = datetime.fromtimestamp(ws, timezone.utc)
    return dt.strftime("%m-%d %H:%M"), dt.hour

rows = []
# z-maker + sol maker (maker schema)
for f, eng in [("data/multi_window_engine_live.jsonl", "zmaker"), ("data/multi_window_engine_sol_live.jsonl", "solmkr")]:
    for o in ld(ROOT+"/"+f):
        if o.get("filled") is True and o.get("won") is not None and o.get("pnl") is not None:
            t, h = hourof(o.get("slug", ""))
            rows.append({"eng": eng, "t": t, "hr": h, "coin": o.get("coin"), "side": o.get("side"),
                         "won": o.get("won"), "price": o.get("B"), "lead": o.get("lead"), "maxlead": o.get("max_lead"),
                         "persist": o.get("persist"), "accel": o.get("accel"), "z": o.get("zscore"),
                         "vol": o.get("vol30"), "btcvol": None, "off": None, "flip": None, "sh": o.get("sh"), "pnl": o.get("pnl")})
# taker (taker schema)
for o in ld(ROOT+"/data/early_taker_probe.jsonl"):
    if o.get("kind") == "entry" and o.get("won") is not None and o.get("pnl") is not None:
        t, h = hourof(o.get("slug", ""))
        rows.append({"eng": "taker", "t": t, "hr": h, "coin": o.get("coin"), "side": o.get("side"),
                     "won": o.get("won"), "price": o.get("paid"), "lead": o.get("lead2") or o.get("lead"), "maxlead": None,
                     "persist": None, "accel": None, "z": o.get("zscore"), "vol": o.get("coin_vol30"),
                     "btcvol": o.get("btc_vol"), "off": o.get("offset"), "flip": o.get("flip60"), "sh": 5, "pnl": o.get("pnl")})
loss = [r for r in rows if not r["won"]]; win = [r for r in rows if r["won"]]
# CSV
with open(ROOT+"/data/losses_dump.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["eng", "t", "hr", "coin", "side", "price", "lead", "maxlead", "persist", "accel", "z", "vol", "btcvol", "off", "flip", "sh", "pnl"])
    w.writeheader()
    for r in sorted(loss, key=lambda x: (x["eng"], x["t"] or "")):
        w.writerow({k: r[k] for k in w.fieldnames})
print(f"wrote {len(loss)} losses -> data/losses_dump.csv\n")

def tbl(rs, cols, hdr):
    print("  " + hdr)
    for r in rs:
        print("  " + " ".join(f"{str(r[c]) if r[c] is not None else '-':>{w}}" for c, w in cols))

MK = [("t",11),("coin",4),("side",4),("price",5),("lead",6),("maxlead",7),("persist",7),("accel",6),("z",5),("vol",5),("sh",3),("pnl",6)]
print("=== Z-MAKER LOSSES (%d) — sorted by time ===" % len([r for r in loss if r["eng"]=="zmaker"]))
tbl(sorted([r for r in loss if r["eng"]=="zmaker"], key=lambda x: x["t"] or ""), MK,
    f"{'time':>11} {'coin':>4} {'side':>4} {'price':>5} {'lead':>6} {'maxlead':>7} {'persist':>7} {'accel':>6} {'z':>5} {'vol':>5} {'sh':>3} {'pnl':>6}")

TK = [("t",11),("coin",4),("side",4),("price",5),("lead",6),("z",5),("vol",5),("btcvol",6),("off",4),("flip",5),("pnl",6)]
tl = sorted([r for r in loss if r["eng"]=="taker"], key=lambda x: x["t"] or "")
print(f"\n=== TAKER LOSSES ({len(tl)}) — sorted by time ===")
tbl(tl, TK, f"{'time':>11} {'coin':>4} {'side':>4} {'price':>5} {'lead':>6} {'z':>5} {'vol':>5} {'btcvol':>6} {'off':>4} {'flip':>5} {'pnl':>6}")

print(f"\n=== SOL MAKER LOSSES ({len([r for r in loss if r['eng']=='solmkr'])}) ===")
tbl([r for r in loss if r["eng"]=="solmkr"], MK, "")

# winner baselines for comparison
def med(rs, k):
    v = [r[k] for r in rs if r.get(k) is not None]
    return f"{st.median(v):.2f} [{min(v):.1f}..{max(v):.1f}]" if v else "-"
print("\n=== WINNER baselines (for comparison) ===")
for eng in ("zmaker", "taker"):
    w = [r for r in win if r["eng"] == eng]; ll = [r for r in loss if r["eng"] == eng]
    print(f"  {eng}: n_win={len(w)} n_loss={len(ll)}")
    for k in ("price", "lead", "maxlead", "persist", "accel", "z", "vol", "btcvol", "off", "flip"):
        wm = med(w, k); lm = med(ll, k)
        if wm != "-" or lm != "-": print(f"     {k:8s} WIN {wm:24s} LOSS {lm}")
