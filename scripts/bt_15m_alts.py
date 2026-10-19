"""bt_15m_alts.py — SCREEN the 15m directional signal on ALL 6 coins, month-scale, binance-only.
For each coin: enumerate 15m windows, LATE entry (min9-14, first qualifying), report win% at lead>=8 and
at +z>=2.5 (z=|lead|/coin_own_vol30, the live z-maker gate), frequency, and trend/chop split.
PRICE-INDEPENDENT win% screen only — does the SIGNAL exist on alt 15m? Execution (spread/fill) still
needs DRY (this just decides which alts are worth DRY-observing). binance-resolution proxy caveat."""
import sys, math, time, statistics as st, httpx
NDAYS = int(sys.argv[sys.argv.index("--days")+1]) if "--days" in sys.argv else 30
SYMS = {"btc": "BTCUSDT", "eth": "ETHUSDT", "sol": "SOLUSDT", "xrp": "XRPUSDT", "doge": "DOGEUSDT", "bnb": "BNBUSDT"}
now = int(time.time()); t1 = now//60*60; t0 = t1 - NDAYS*86400 - 2400
def fetch(sym):
    out = {}; cur = t0
    with httpx.Client() as c:
        while cur < t1:
            try:
                r = c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m",
                          "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
            except: break
            if not isinstance(r, list) or not r: break
            for k in r: out[int(k[0]//1000)] = (float(k[1]), float(k[4]))
            cur = int(r[-1][0]//1000)+60
    return out

# btc series for regime vol (the regime label uses btc_vol per the month-finding)
print(f"fetching {NDAYS}d for {len(SYMS)} coins...")
SER = {}
for coin, sym in SYMS.items():
    SER[coin] = fetch(sym); print(f"  {coin}: {len(SER[coin])} min")
btc = SER["btc"]
def btc_vol_at(ts):
    m0 = ts//60*60; cl = [btc[m0-i*60][1] for i in range(31) if (m0-i*60) in btc]
    if len(cl) < 20: return None
    cl = cl[::-1]; rets = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]
    return st.pstdev(rets)

def windows_for(coin):
    ser = SER[coin]; out = []; w0 = (t0+2400)//900*900; ws = w0
    while ws+900 <= t1:
        op = ser.get(ws); cl14 = ser.get(ws+14*60)
        if not op or not cl14: ws += 900; continue
        o = op[0]; leads = {}
        for m in range(0, 15):
            c = ser.get(ws+m*60); leads[m] = (math.log(c[1]/o)*1e4) if c else None
        # own vol30 at each late minute
        vols = {}
        for m in range(9, 15):
            m0 = ws+m*60; cl = [ser[m0-i*60][1] for i in range(31) if (m0-i*60) in ser]
            if len(cl) >= 20:
                cl = cl[::-1]; rets = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]; vols[m] = st.pstdev(rets)
            else: vols[m] = None
        up_win = ser[ws+14*60][1] >= o
        seq = [leads[m] for m in range(1, 10) if leads.get(m) is not None]
        if len(seq) < 5: ws += 900; continue
        flips = sum(1 for i in range(1, len(seq)) if (seq[i] >= 0) != (seq[i-1] >= 0))
        pk9 = max((abs(x) for x in seq), default=0.0); l9 = leads.get(9)
        persist = (abs(l9)/pk9) if (l9 is not None and pk9 > 0) else 0.0
        bv = btc_vol_at(ws+9*60)
        out.append({"up_win": up_win, "leads": leads, "vols": vols,
                    "path": "trend" if (flips <= 1 and persist >= 0.7) else "chop"})
        ws += 900
    return out

def late_winrate(rows, z_min=0):
    w = n = 0
    for d in rows:
        for m in range(9, 15):
            l = d["leads"].get(m)
            if l is None or abs(l) < 8: continue
            if z_min > 0:
                v = d["vols"].get(m)
                if not v or abs(l)/v < z_min: continue
            n += 1; w += ((l >= 0) == d["up_win"]); break
    return (w/n*100, n) if n else (0, 0)

print(f"\n{'coin':5s} {'windows':>8s} | {'lead>=8 win/n':>16s} | {'+z>=2.5 win/n':>16s} | {'z-fire%':>7s} | trend/chop win%")
print("-"*92)
for coin in SYMS:
    rows = windows_for(coin)
    if not rows: print(f"{coin}: no data"); continue
    w8, n8 = late_winrate(rows, 0); wz, nz = late_winrate(rows, 2.5)
    tr = [d for d in rows if d["path"] == "trend"]; ch = [d for d in rows if d["path"] == "chop"]
    twr = late_winrate(tr, 0)[0]; cwr = late_winrate(ch, 0)[0]
    firepct = nz/len(rows)*100
    print(f"{coin:5s} {len(rows):8d} | {w8:5.1f}%/{n8:<8d} | {wz:5.1f}%/{nz:<8d} | {firepct:5.1f}% | {twr:.0f}% / {cwr:.0f}%")
print("\nNOTE: binance-resolution proxy + win%-ONLY (priced-in). High win% = signal EXISTS, NOT that it's "
      "profitable — alt spreads (2c+) eat it. This screens which alts merit a DRY (execution) test; sol was "
      "the only +EV alt on 5m, xrp/doge -EV, bnb thin. DRY measures the real spread/fill that decides $.")
