"""bt_circuit_breaker.py — validate the loss-clustering finding:
(1) VOL-CONTROL: within vol buckets, does rolling-10 loss-count still predict next loss? (independent of vol?)
(2) CIRCUIT-BREAKER EV: simulate pausing/downsizing the 20sh CELL when rolling-10 losses >= K, using REAL
    pnl, time-ordered. Report net PnL vs baseline, on ALL + held-out last-40% (which contains the drawdown).
Rolling signal = combined taker+zmaker outcome stream (market-wide regime proxy)."""
import json, math, re, statistics as st, time, httpx
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
F = []
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl", encoding="utf-8") if l.strip()):
    if o.get("kind") == "entry" and o.get("won") is not None:
        m = re.search(r"-5m-(\d+)", o.get("slug", ""))
        if m: F.append({"ws": int(m.group(1)), "won": bool(o["won"]), "pnl": float(o.get("pnl", 0)), "sh": 5, "eng": "taker"})
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None:
        m = re.search(r"-5m-(\d+)", o.get("slug", ""))
        if m: F.append({"ws": int(m.group(1)), "won": bool(o["won"]), "pnl": float(o.get("pnl", 0)), "sh": int(o.get("sh", 5)), "eng": "zmaker"})
F.sort(key=lambda x: x["ws"])
n = len(F)
# rolling-10 loss count BEFORE each fill (combined stream)
for i in range(n):
    F[i]["roll"] = sum(1 for f in F[max(0, i-10):i] if not f["won"])
# btc vol at each ws
t0 = min(f["ws"] for f in F)-2400; t1 = max(f["ws"] for f in F)+600
print("fetching btc 1m...")
BTC = {}; cur = t0
with httpx.Client() as c:
    while cur < t1:
        r = c.get("https://api.binance.com/api/v3/klines", params={"symbol": "BTCUSDT", "interval": "1m", "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
        if not isinstance(r, list) or not r: break
        for k in r: BTC[int(k[0]//1000)] = float(k[4])
        cur = int(r[-1][0]//1000)+60
def vol(ws):
    seq = [BTC[ws-i*60] for i in range(30, -1, -1) if (ws-i*60) in BTC]
    if len(seq) < 20: return None
    rr = [math.log(seq[i]/seq[i-1])*1e4 for i in range(1, len(seq))]; return st.pstdev(rr)
for f in F: f["vol"] = vol(f["ws"])
F = [f for f in F if f["vol"] is not None]
n = len(F)

print(f"\n=== (1) VOL-CONTROL: is clustering independent of vol? ({n} fills) ===")
for lab, sub in (("LOW vol (<6.5)", [f for f in F if f["vol"] < 6.5]), ("HIGH vol (>=6.5)", [f for f in F if f["vol"] >= 6.5])):
    hot = [f for f in sub if f["roll"] >= 3]; cool = [f for f in sub if f["roll"] < 3]
    if hot and cool:
        hl = sum(1 for f in hot if not f["won"])/len(hot)*100; cl = sum(1 for f in cool if not f["won"])/len(cool)*100
        print(f"  {lab:16s}: rolling>=3 loss%={hl:5.1f} (n={len(hot):3d}) | <3 loss%={cl:5.1f} (n={len(cool):3d}) | lift {hl-cl:+.1f}pp")
print("  (if lift stays +ve in LOW-vol -> clustering is INDEPENDENT of vol, a real separate regime signal)")

def sim(fills, K, mode):
    base = sum(f["pnl"] for f in fills); adj = 0.0; touched = 0; avoided_loss = 0.0; forgone_win = 0.0
    for f in fills:
        p = f["pnl"]
        if f["eng"] == "zmaker" and f["sh"] == 20 and f["roll"] >= K:
            touched += 1
            if mode == "down":   # 20->5 sh
                newp = p*(5.0/20.0)
            else:                # skip
                newp = 0.0
            if p < 0: avoided_loss += (p-newp)   # negative*... reduces loss (p-newp<0 means we saved)
            else: forgone_win += (p-newp)
            adj += newp
        else:
            adj += p
    return base, adj, touched, avoided_loss, forgone_win

cut = int(n*0.6); TRAIN, TEST = F[:cut], F[cut:]
print(f"\n=== (2) CIRCUIT-BREAKER EV (cell 20sh, pause/downsize when rolling>=K) ===")
print(f"  {'set':6s} {'K':>2s} {'mode':5s} {'baseline$':>10s} {'with-breaker$':>13s} {'delta$':>8s} {'cellTouched':>11s}")
for setlab, fset in (("ALL", F), ("TEST40%", TEST)):
    for K in (2, 3):
        for mode in ("down", "skip"):
            b, a, t, al, fw = sim(fset, K, mode)
            print(f"  {setlab:6s} {K:>2d} {mode:5s} {b:10.2f} {a:13.2f} {a-b:+8.2f} {t:11d}")
print("\n  delta>0 = breaker improves net PnL. 'down'=20->5sh, 'skip'=no cell. TEST40% contains the drawdown.")
print("  NOTE: in-sample-ish; the rolling rule has 1 param (K). If delta>0 on TEST (incl drawdown) AND")
print("  vol-control shows independence -> a real, deployable circuit breaker. Else -> variance.")
