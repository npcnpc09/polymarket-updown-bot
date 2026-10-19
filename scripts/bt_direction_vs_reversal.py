"""bt_direction_vs_reversal.py — are the losses DIRECTION errors or REVERSALS?
For every real loss, reconstruct from binance: did price move OUR way during the window (favorable
excursion) before settling against us (=REVERSAL, direction was right), or did it never go our way
(=WRONG DIRECTION from the start)? Quantifies the premise."""
import json, re, math, statistics as st, time, httpx
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
BSYM = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
L = []
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl", encoding="utf-8") if l.strip()):
    if o.get("kind") == "entry" and o.get("won") is False:
        m = re.search(r"(btc|eth)-updown-5m-(\d+)", o.get("slug", ""))
        if m: L.append({"coin": m.group(1), "ws": int(m.group(2)), "side": o.get("side")})
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is False:
        m = re.search(r"(btc|eth)-updown-5m-(\d+)", o.get("slug", ""))
        if m: L.append({"coin": m.group(1), "ws": int(m.group(2)), "side": o.get("side")})
print(f"{len(L)} real losses")
t0 = min(x["ws"] for x in L)-200; t1 = max(x["ws"] for x in L)+400
def fetch(sym):
    out = {}; cur = t0
    with httpx.Client() as c:
        while cur < t1:
            r = c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
            if not isinstance(r, list) or not r: break
            for k in r: out[int(k[0]//1000)] = (float(k[1]), float(k[4]))
            cur = int(r[-1][0]//1000)+60
    return out
SER = {c: fetch(s) for c, s in BSYM.items()}
rev = wrong = flat = 0; fav_exc = []
for x in L:
    ser = SER[x["coin"]]; ws = x["ws"]
    if ws not in ser: continue
    o = ser[ws][0]; sgn = 1 if x["side"] == "Up" else -1
    # leads each minute, signed toward OUR bet
    leads = []
    for mm in range(0, 5):
        c = ser.get(ws+mm*60)
        if c: leads.append(math.log(c[1]/o)*1e4*sgn)
    if len(leads) < 4: continue
    maxfav = max(leads)            # best the price got in OUR direction (bps)
    settle = leads[-1]             # settle in our direction (negative = we lost)
    fav_exc.append(maxfav)
    if maxfav >= 8: rev += 1       # price went >=8bps OUR way at some point -> direction was RIGHT, then reversed
    elif maxfav <= 2: wrong += 1   # never meaningfully went our way -> arguably wrong direction
    else: flat += 1
tot = rev+wrong+flat
print(f"\n=== of {tot} losses, was the DIRECTION right (then reversed) or wrong-from-start? ===")
print(f"  REVERSAL (price went >=8bps OUR way, then reversed to lose): {rev} ({rev/tot*100:.0f}%)")
print(f"  FLAT (peak 2-8bps our way):                                  {flat} ({flat/tot*100:.0f}%)")
print(f"  WRONG-FROM-START (never went >2bps our way):                 {wrong} ({wrong/tot*100:.0f}%)")
print(f"\n  median favorable excursion before losing = {st.median(fav_exc):.1f} bps")
print(f"  => if most losses had a big favorable excursion, the entry DIRECTION was correct; the loss is a")
print(f"     REVERSAL, not a direction-selection error. Direction-picking can't fix a post-entry reversal.")
