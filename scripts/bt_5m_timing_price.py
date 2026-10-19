"""bt_5m_timing_price.py — PART 2 of entry-timing: the PRICE COST of waiting -> the buy-below-fair edge.
For recent 5m windows: binance lead/min + REAL PM price/min (prices-history). At each entry minute,
among gated windows (|lead|>=8), compute win%, avg PM favorite price, and EDGE = win% - price (the gap
between true win-prob and what the market charges = the maker buy-below-fair edge). The minute that
MAXIMIZES edge = optimal entry timing. Also splits by z>=2.5."""
import json, math, sys, httpx, statistics as st
from concurrent.futures import ThreadPoolExecutor
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
BSYM = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
NPER = int(sys.argv[1]) if len(sys.argv) > 1 else 600
wins = []
for ln in open(ROOT+"/data/updown_tokens.jsonl", encoding="utf-8"):
    try: r = json.loads(ln)
    except: continue
    if r.get("dur") == 300 and r.get("coin") in BSYM: wins.append(r)
wins = sorted(wins, key=lambda r: r["start"])[-NPER:]
print(f"{len(wins)} real 5m windows")
def bn(sym, t0, t1):
    out = {}
    try:
        r = httpx.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m",
                      "startTime": t0*1000, "endTime": t1*1000, "limit": 200}, timeout=20).json()
        for k in r:
            if isinstance(k, list): out[int(k[0]//1000)] = (float(k[1]), float(k[4]))
    except: pass
    return out
def ph(tok, st_):
    try:
        r = httpx.get("https://clob.polymarket.com/prices-history", params={"market": tok, "startTs": st_-120,
                      "endTs": st_+300+120, "fidelity": "1"}, timeout=15).json()
        h = r.get("history", []) if isinstance(r, dict) else []
        return {int(x["t"]//60): float(x["p"]) for x in h}
    except: return {}
def job(w):
    coin, st_, up = w["coin"], w["start"], w["up"]
    bnd = bn(BSYM[coin], st_-1860, st_+360)
    if st_ not in bnd: return None
    o = bnd[st_][0]; h = ph(up, st_)
    if len(h) < 4: return None
    m0 = st_//60; up_win = h[max(h)] >= 0.5
    rec = {"up_win": up_win, "min": {}}
    for m in range(1, 5):
        c = bnd.get((m0+m)*60)
        if not c: continue
        lead = math.log(c[1]/o)*1e4
        cl = [bnd[(m0+m-i)*60][1] for i in range(31) if (m0+m-i)*60 in bnd]
        v = None
        if len(cl) >= 20:
            cl = cl[::-1]; rets = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]; v = st.pstdev(rets)
        side_up = lead >= 0
        # PM price of the LEADING side at minute m
        pm = None
        for d in range(0, 3):
            if (m0+m-d) in h: pm = h[m0+m-d]; break
        if pm is not None and not side_up: pm = 1-pm
        rec["min"][m] = {"lead": lead, "v": v, "side_up": side_up, "pm": pm}
    return rec
data = []
with ThreadPoolExecutor(max_workers=12) as ex:
    for i, r in enumerate(ex.map(job, wins)):
        if r: data.append(r)
        if i % 100 == 0: print(f"  {i}/{len(wins)}")
print(f"usable {len(data)}\n")

def curve(z=0):
    print(f"=== entry-timing edge {'(z>=2.5)' if z else '(|lead|>=8)'} ===")
    print(f"  {'entry':6s} {'n':>5s} {'win%':>6s} {'avgPMprice':>11s} {'EDGE=win-price':>15s}")
    for m in range(1, 5):
        rows = []
        for d in data:
            x = d["min"].get(m)
            if not x or abs(x["lead"]) < 8 or x["pm"] is None: continue
            if z > 0 and (not x["v"] or abs(x["lead"])/x["v"] < z): continue
            rows.append((x["pm"], (x["side_up"] == d["up_win"])))
        if not rows: print(f"  min{m}: none"); continue
        n = len(rows); w = sum(1 for p, won in rows if won)/n
        avgp = sum(p for p, _ in rows)/n
        print(f"  min{m:<3d} {n:5d} {w*100:5.1f}% {avgp:10.3f}  {(w-avgp)*100:+13.1f}pp")
curve(0)
print()
curve(2.5)
print("\nEDGE = true win% minus what the market charges for the favorite. Positive = buy-below-fair room "
      "(maker edge). The minute maximizing EDGE = optimal entry; after that the price catches up to win%.")
