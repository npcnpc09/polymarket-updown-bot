"""bt_15m_month.py — MONTH-scale validation of the 15m REGIME win-rate finding, binance-only.
Fetches ~NDAYS of btc+eth 1m klines as ONE continuous series each (cheap), then enumerates every
15m window offline and labels regime AT MIN9 (live-knowable): VOL (btc_vol30<6.5) & PATH (flips/persist).
Resolution = binance close@settle vs open (Chainlink proxy; tight calls -> noisier, cluster in chop).
PRICE-INDEPENDENT: validates baseline lead-side win% per regime + the directional strategy's win% over
a large sample. No PM price -> no EV (memory: fill-model EV untrustworthy anyway; win% is the robust read)."""
import sys, math, time, statistics as st, httpx
NDAYS = int(sys.argv[sys.argv.index("--days")+1]) if "--days" in sys.argv else 30
SYMS = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
RCM = 9   # regime-classification minute
now = int(time.time())
t1 = now//60*60
t0 = t1 - NDAYS*86400 - 2400

def fetch_series(sym):
    out = {}
    cur = t0
    with httpx.Client() as c:
        while cur < t1:
            r = c.get("https://api.binance.com/api/v3/klines",
                      params={"symbol": sym, "interval": "1m", "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
            if not isinstance(r, list) or not r: break
            for k in r: out[int(k[0]//1000)] = (float(k[1]), float(k[4]))  # (open, close)
            cur = int(r[-1][0]//1000) + 60
    return out

print(f"fetching {NDAYS}d of 1m klines (btc+eth)...")
SER = {coin: fetch_series(sym) for coin, sym in SYMS.items()}
for coin in SER: print(f"  {coin}: {len(SER[coin])} minutes")
btc = SER["btc"]
def btc_vol_at(ts):
    m0 = ts//60*60
    cl = [btc[m0-i*60][1] for i in range(31) if (m0-i*60) in btc]
    if len(cl) < 20: return None
    cl = cl[::-1]; rets = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]
    return st.pstdev(rets)

windows = []
for coin in SYMS:
    ser = SER[coin]
    w0 = (t0+2400)//900*900
    ws = w0
    while ws + 900 <= t1:
        op = ser.get(ws)
        cl14 = ser.get(ws+14*60)
        if not op or not cl14: ws += 900; continue
        open_px = op[0]
        leads = {}
        for m in range(0, 15):
            c = ser.get(ws+m*60)
            leads[m] = (math.log(c[1]/open_px)*1e4) if c else None
        # vol30 (own coin) at min9
        m0 = (ws+RCM*60)
        cl = [ser[m0-i*60][1] for i in range(31) if (m0-i*60) in ser]
        vol9 = None
        if len(cl) >= 20:
            cl = cl[::-1]; rets = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]; vol9 = st.pstdev(rets)
        up_win = ser[ws+14*60][1] >= open_px
        seq = [leads[m] for m in range(1, RCM+1) if leads.get(m) is not None]
        if len(seq) < 5: ws += 900; continue
        flips = sum(1 for i in range(1, len(seq)) if (seq[i] >= 0) != (seq[i-1] >= 0))
        pk9 = max((abs(x) for x in seq), default=0.0)
        persist = (abs(seq[-1])/pk9) if pk9 > 0 else 0.0
        bv = btc_vol_at(ws+RCM*60)
        windows.append({"coin": coin, "ws": ws, "up_win": up_win, "leads": leads, "vol9": vol9,
                        "bv9": bv, "flips9": flips, "persist9": round(persist, 2),
                        "vol_reg": ("calm" if (bv is not None and bv < 6.5) else "volatile") if bv is not None else "unk",
                        "path_reg": "trend" if (flips <= 1 and persist >= 0.7) else "chop"})
        ws += 900
print(f"\nenumerated {len(windows)} 15m windows over {NDAYS}d\n")

def base(rows, lead_min=8, m=10):
    w = n = 0
    for d in rows:
        l = d["leads"].get(m)
        if l is None or abs(l) < lead_min: continue
        n += 1; w += ((l >= 0) == d["up_win"])
    return (w/n*100, n) if n else (0, 0)

def strat(rows, lead_min, z_min, ml_min, mlo=9, mhi=15):
    """late directional: first min in [mlo,mhi) with |lead|>=lead_min, z>=z_min, peak>=ml_min."""
    w = n = 0
    for d in rows:
        L = d["leads"]
        for mm in range(mlo, mhi):
            l = L.get(mm)
            if l is None or abs(l) < lead_min: continue
            pk = max((abs(L[k]) for k in range(0, mm+1) if L.get(k) is not None), default=0.0)
            v = d["vol9"]
            if z_min > 0 and (not v or abs(l)/v < z_min): continue
            if ml_min > 0 and pk < ml_min: continue
            n += 1; w += ((l >= 0) == d["up_win"]); break
    return (w/n*100, n) if n else (0, 0)

regimes = {
    "ALL": windows,
    "trend": [d for d in windows if d["path_reg"] == "trend"],
    "chop": [d for d in windows if d["path_reg"] == "chop"],
    "calm": [d for d in windows if d["vol_reg"] == "calm"],
    "volatile": [d for d in windows if d["vol_reg"] == "volatile"],
    "calm+trend": [d for d in windows if d["vol_reg"] == "calm" and d["path_reg"] == "trend"],
    "calm+chop": [d for d in windows if d["vol_reg"] == "calm" and d["path_reg"] == "chop"],
    "volatile+trend": [d for d in windows if d["vol_reg"] == "volatile" and d["path_reg"] == "trend"],
    "volatile+chop": [d for d in windows if d["vol_reg"] == "volatile" and d["path_reg"] == "chop"],
}
print("regime sizes:", {k: len(v) for k, v in regimes.items()})
# split in halves by time to check stability
mid_ts = sorted(d["ws"] for d in windows)[len(windows)//2]

print(f"\n{'regime':16s} {'n':>5s} {'base win%':>9s} | {'trend-strat':>11s} | {'chop-strat(z2/ml20)':>20s} | half1/half2 base")
print("-"*92)
for rname, rows in regimes.items():
    if len(rows) < 30:
        print(f"{rname:16s} {len(rows):5d}  (too small)"); continue
    bw, bn = base(rows)
    tw, tn = strat(rows, 8, 0, 0)          # trend-style: loose late directional
    cw, cn = strat(rows, 8, 2.0, 20)       # chop-style: strict
    h1 = [d for d in rows if d["ws"] < mid_ts]; h2 = [d for d in rows if d["ws"] >= mid_ts]
    b1 = base(h1)[0]; b2 = base(h2)[0]
    print(f"{rname:16s} {len(rows):5d}  {bw:7.1f}%  | {tw:6.1f}%/{tn:<4d}| {cw:6.1f}%/{cn:<4d}        | {b1:.0f}%/{b2:.0f}%")
print("\nNOTE: binance-resolution proxy (tight calls noisier, cluster in chop -> chop win% slightly "
      "understated vs real Chainlink). win% only (no PM price). half1/half2 = time-stability check.")
