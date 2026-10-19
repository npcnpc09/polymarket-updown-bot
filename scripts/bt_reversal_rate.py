"""bt_reversal_rate.py — a DIRECT market REVERSAL-RATE regime indicator (vs the lagging outcome-breaker).
RR_N[coin] = over the last N qualifying 5m windows (|early lead@min2|>=8), the fraction where the early
lead DIRECTION != settle direction (= a reversal). Computed from binance price only, every window, per
coin -> LEADS our losses (market turns reversal-prone before our specific windows resolve).
Tests: (a) on 30d cell-eligible signal, win% by RR bucket; (b) on REAL live fills, real loss% by RR
bucket; (c) vol-control; (d) does RR at entry beat the rolling-10-loss breaker (lead vs lag)?"""
import json, re, math, time, statistics as st, httpx
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
BSYM = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
now = int(time.time()); t1 = now//60*60; t0 = t1 - 30*86400 - 2400
def fetch(sym):
    out = {}; cur = t0
    with httpx.Client() as c:
        while cur < t1:
            r = c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
            if not isinstance(r, list) or not r: break
            for k in r: out[int(k[0]//1000)] = (float(k[1]), float(k[4]))
            cur = int(r[-1][0]//1000)+60
    return out
print("fetching 30d btc+eth...")
SER = {c: fetch(s) for c, s in BSYM.items()}

# per-coin per-window: early lead (min2), settle, reversal flag (only qualifying |early|>=8); + trailing RR12
WIN = {c: {} for c in BSYM}   # coin -> {ws: {...}}
RR = {c: {} for c in BSYM}    # coin -> {ws: trailing reversal-rate before this window}
for coin in BSYM:
    ser = SER[coin]; ws = (t0+2400)//300*300; hist = []
    while ws+300 <= t1:
        op = ser.get(ws); c2 = ser.get(ws+120); c4 = ser.get(ws+240)
        if op and c2 and c4:
            o = op[0]; early = math.log(c2[1]/o)*1e4; settle = math.log(c4[1]/o)*1e4
            qual = abs(early) >= 8
            reversed_ = qual and ((early >= 0) != (settle >= 0))
            # trailing RR over last 12 QUALIFYING windows (before this one)
            recent = [h for h in hist if h["qual"]][-12:]
            RR[coin][ws] = (sum(1 for h in recent if h["rev"])/len(recent)) if len(recent) >= 6 else None
            WIN[coin][ws] = {"early": early, "settle": settle, "qual": qual, "rev": reversed_}
            hist.append({"qual": qual, "rev": reversed_})
        ws += 300

# vol helper
def vol(coin, ws):
    ser = SER[coin]; seq = [ser[ws-i*60][1] for i in range(31) if (ws-i*60) in ser]
    if len(seq) < 20: return None
    rr = [math.log(seq[i]/seq[i-1])*1e4 for i in range(1, len(seq))]; return st.pstdev(rr)

# (a) 30d cell-eligible signal: win% by RR bucket
print("\n=== (a) 30d cell-eligible (late z>=2.5) win% by trailing reversal-rate RR12 ===")
elig = []
for coin in BSYM:
    ser = SER[coin]; ws = (t0+2400)//300*300
    while ws+300 <= t1:
        op = ser.get(ws); c4 = ser.get(ws+240)
        if op and c4:
            o = op[0]; up_win = c4[1] >= o
            for m in (3, 4):
                cc = ser.get(ws+m*60)
                if not cc: continue
                l = math.log(cc[1]/o)*1e4
                if abs(l) < 8: continue
                v = vol(coin, ws+m*60)
                if not v or abs(l)/v < 2.5: continue
                elig.append({"coin": coin, "ws": ws, "won": ((l >= 0) == up_win), "rr": RR[coin].get(ws), "vol": v}); break
        ws += 300
elig = [e for e in elig if e["rr"] is not None]
for lo, hi in ((0, 0.15), (0.15, 0.30), (0.30, 0.50), (0.50, 1.01)):
    sub = [e for e in elig if lo <= e["rr"] < hi]
    if sub:
        w = sum(1 for e in sub if e["won"]); print(f"  RR12 [{lo:.2f},{hi:.2f}): n={len(sub):5d} win%={w/len(sub)*100:5.2f} loss%={100-w/len(sub)*100:4.2f}")

# (b) REAL live fills: real loss% by RR bucket
print("\n=== (b) REAL live fills loss% by RR12 at entry ===")
F = []
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl", encoding="utf-8") if l.strip()):
    if o.get("kind") == "entry" and o.get("won") is not None:
        m = re.search(r"(btc|eth)-updown-5m-(\d+)", o.get("slug", ""))
        if m: F.append({"coin": m.group(1), "ws": int(m.group(2)), "won": bool(o["won"])})
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None:
        m = re.search(r"(btc|eth)-updown-5m-(\d+)", o.get("slug", ""))
        if m: F.append({"coin": m.group(1), "ws": int(m.group(2)), "won": bool(o["won"])})
for f in F: f["rr"] = RR[f["coin"]].get(f["ws"])
F = [f for f in F if f["rr"] is not None]
print(f"  {len(F)} real fills matched to RR")
for lo, hi in ((0, 0.15), (0.15, 0.30), (0.30, 0.50), (0.50, 1.01)):
    sub = [f for f in F if lo <= f["rr"] < hi]
    if len(sub) >= 15:
        L = sum(1 for f in sub if not f["won"]); print(f"  RR12 [{lo:.2f},{hi:.2f}): n={len(sub):4d} loss%={L/len(sub)*100:5.1f}")
# (c) vol-control: within low-vol, does RR still separate?
print("\n=== (c) vol-control (real fills, btc-vol proxy via own coin vol) ===")
for f in F: f["v"] = vol(f["coin"], f["ws"])
lowv = [f for f in F if f["v"] is not None and f["v"] < 6.5]
for lab, pred in (("RR>=0.30", lambda f: f["rr"] >= 0.30), ("RR<0.30", lambda f: f["rr"] < 0.30)):
    sub = [f for f in lowv if pred(f)]
    if sub: L = sum(1 for f in sub if not f["won"]); print(f"  low-vol & {lab}: n={len(sub):4d} loss%={L/len(sub)*100:5.1f}")
print("\nVERDICT: if loss% rises monotonically with RR12, and stays separated in low-vol -> RR is a DIRECT,")
print("LEADING reversal-regime indicator (updates every window, not just our fills) -> better gate than the")
print("lagging outcome-breaker, or a complement. If flat -> reversals aren't autocorrelated at market level.")
