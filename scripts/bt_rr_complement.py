"""bt_rr_complement.py — can RR be USEFULLY used as a LEADING complement to the (deployed) outcome breaker?
Two clean tests (not parameter-mining):
 (1) LEAD: when the breaker arms (rolling-10 losses >=2), was RR already elevated in the windows BEFORE?
     i.e. does RR rise ahead of our realized loss-cluster (early warning)?
 (2) COMPOSITE EV: cell circuit-breaker triggered by  (a) rolling>=2 [current]  (b) rolling>=2 OR RR>=thr
     (c) RR>=thr alone. Does adding RR improve net cell PnL over the breaker alone?
RR = min2 ref, N=12 (the original). Uses REAL fills + real pnl, time-ordered."""
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
def build_RR(coin, N=12):
    ser = SER[coin]; ws = (t0+2400)//300*300; hist = []; RR = {}
    while ws+300 <= t1:
        op = ser.get(ws); cref = ser.get(ws+120); cend = ser.get(ws+240)
        if op and cref and cend:
            o = op[0]; early = math.log(cref[1]/o)*1e4; settle = math.log(cend[1]/o)*1e4
            q = abs(early) >= 8; rev = q and ((early >= 0) != (settle >= 0))
            recent = [h for h in hist if h["q"]][-N:]
            RR[ws] = (sum(1 for h in recent if h["r"])/len(recent)) if len(recent) >= 6 else None
            hist.append({"q": q, "r": rev})
        ws += 300
    return RR
RRc = {c: build_RR(c) for c in BSYM}
F = []
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl", encoding="utf-8") if l.strip()):
    if o.get("kind") == "entry" and o.get("won") is not None:
        m = re.search(r"(btc|eth)-updown-5m-(\d+)", o.get("slug", ""))
        if m: F.append({"coin": m.group(1), "ws": int(m.group(2)), "won": bool(o["won"]), "pnl": float(o.get("pnl", 0)), "sh": 5, "eng": "taker"})
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None:
        m = re.search(r"(btc|eth)-updown-5m-(\d+)", o.get("slug", ""))
        if m: F.append({"coin": m.group(1), "ws": int(m.group(2)), "won": bool(o["won"]), "pnl": float(o.get("pnl", 0)), "sh": int(o.get("sh", 5)), "eng": "zmaker"})
F.sort(key=lambda x: x["ws"])
for i, f in enumerate(F):
    f["roll"] = sum(1 for x in F[max(0, i-10):i] if not x["won"]); f["rr"] = RRc[f["coin"]].get(f["ws"])
FA = [f for f in F if f["rr"] is not None]
print(f"{len(FA)} fills with RR\n")

# (1) LEAD: RR around breaker-arm events
print("=== (1) does RR lead the breaker? ===")
base_rr = st.median([f["rr"] for f in FA])
arm_idx = [i for i in range(1, len(FA)) if FA[i]["roll"] >= 2 and FA[i-1]["roll"] < 2]  # moment breaker arms
print(f"  baseline median RR = {base_rr:.3f} | breaker-arm events = {len(arm_idx)}")
for lag in (3, 2, 1, 0):
    vals = [FA[i-lag]["rr"] for i in arm_idx if i-lag >= 0]
    if vals: print(f"    RR {lag} fills BEFORE arm: median={st.median(vals):.3f} (vs base {base_rr:.3f})")

# (2) COMPOSITE EV
def sim(trigger):
    base = sum(f["pnl"] for f in FA); adj = 0.0; touched = 0
    for f in FA:
        p = f["pnl"]
        if f["eng"] == "zmaker" and f["sh"] == 20 and trigger(f):
            adj += p*(5.0/20.0); touched += 1
        else: adj += p
    return adj-base, touched
print("\n=== (2) composite EV (cell 20->5sh when triggered) — delta vs no-breaker ===")
for thr in (0.20, 0.30):
    print(f"  RR threshold = {thr}:")
    d0, t0c = sim(lambda f: f["roll"] >= 2)
    d1, t1c = sim(lambda f: f["roll"] >= 2 or f["rr"] >= thr)
    d2, t2c = sim(lambda f: f["rr"] >= thr)
    print(f"    breaker alone (roll>=2)        delta={d0:+.2f} touched={t0c}")
    print(f"    breaker OR RR>={thr}             delta={d1:+.2f} touched={t1c}")
    print(f"    RR>={thr} alone                  delta={d2:+.2f} touched={t2c}")
print("\nREAD: (1) if RR is already > base several fills BEFORE the breaker arms -> RR LEADS = useful early")
print("warning. (2) if 'breaker OR RR' delta > 'breaker alone' -> RR adds value as a complement. Else RR is")
print("redundant/harmful and the honest answer is: can't usefully use RR12; rely on the breaker.")
