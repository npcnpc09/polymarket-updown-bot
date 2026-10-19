"""bt_5m_timing.py — ENTRY-TIMING study for 5m windows, month-scale, binance-only (win%, price-indep).
Question: for our directional signal, does WAITING (later entry) raise win%? and at which minute does it
plateau? Fetches ~NDAYS btc+eth 1m klines, enumerates every 5m window, and for each entry minute m
(offsets 60/120/180/240s) computes win% among windows where the gate holds AT m.
Also the PERSISTENCE view: of windows that fire early (min1/2), how many survive to min3, and does the
survivor win% beat committing early? Resolution = binance close@settle vs open (Chainlink proxy)."""
import sys, math, time, statistics as st, httpx
NDAYS = int(sys.argv[sys.argv.index("--days")+1]) if "--days" in sys.argv else 30
SYMS = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
LEAD = 8.0; ZMIN = 2.5
now = int(time.time()); t1 = now//60*60; t0 = t1 - NDAYS*86400 - 2400
def fetch(sym):
    out = {}; cur = t0
    with httpx.Client() as c:
        while cur < t1:
            r = c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m",
                      "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
            if not isinstance(r, list) or not r: break
            for k in r: out[int(k[0]//1000)] = (float(k[1]), float(k[4]))
            cur = int(r[-1][0]//1000)+60
    return out
print(f"fetching {NDAYS}d 1m klines...")
SER = {c: fetch(s) for c, s in SYMS.items()}
for c in SER: print(f"  {c}: {len(SER[c])} min")

wins = []
for coin in SYMS:
    ser = SER[coin]; w0 = (t0+2400)//300*300; ws = w0
    while ws+300 <= t1:
        op = ser.get(ws); cl4 = ser.get(ws+240)
        if not op or not cl4: ws += 300; continue
        o = op[0]
        leads = {}
        for m in range(0, 5):
            c = ser.get(ws+m*60); leads[m] = (math.log(c[1]/o)*1e4) if c else None
        # vol30 at each entry minute
        vols = {}
        for m in range(1, 5):
            m0 = ws+m*60; cl = [ser[m0-i*60][1] for i in range(31) if (m0-i*60) in ser]
            if len(cl) >= 20:
                cl = cl[::-1]; rets = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]; vols[m] = st.pstdev(rets)
            else: vols[m] = None
        up_win = ser[ws+240][1] >= o
        wins.append({"coin": coin, "ws": ws, "up_win": up_win, "leads": leads, "vols": vols})
        ws += 300
print(f"\nenumerated {len(wins)} 5m windows\n")

def winrate(rows, m, lead=LEAD, z=0):
    w = n = 0
    for d in rows:
        l = d["leads"].get(m)
        if l is None or abs(l) < lead: continue
        if z > 0:
            v = d["vols"].get(m)
            if not v or abs(l)/v < z: continue
        n += 1; w += ((l >= 0) == d["up_win"])
    return (w/n*100, n) if n else (0, 0)

print("=== WIN% BY ENTRY MINUTE (|lead|>=8 at that minute) ===")
print(f"  {'entry':6s} {'offset':7s} {'|lead|>=8':16s} {'+ z>=2.5':16s}  avg|lead|")
for m in range(1, 5):
    w1, n1 = winrate(wins, m, LEAD, 0); w2, n2 = winrate(wins, m, LEAD, ZMIN)
    al = [abs(d["leads"][m]) for d in wins if d["leads"].get(m) is not None and abs(d["leads"][m]) >= LEAD]
    avg = sum(al)/len(al) if al else 0
    print(f"  min{m:<3d} {m*60:4d}s   {w1:5.1f}%/{n1:<6d}  {w2:5.1f}%/{n2:<6d}  {avg:.1f}")

print("\n=== PERSISTENCE: windows firing EARLY (|lead|>=8 at min1), tracked forward ===")
early = [d for d in wins if d["leads"].get(1) is not None and abs(d["leads"][1]) >= LEAD]
print(f"  fired at min1: n={len(early)}")
# commit at min1
cw = sum(1 for d in early if (d["leads"][1] >= 0) == d["up_win"])
print(f"  COMMIT @min1                       win%={cw/len(early)*100:.1f}%")
# wait to min3: require lead still>=8 same side at min3
surv = [d for d in early if d["leads"].get(3) is not None and abs(d["leads"][3]) >= LEAD and (d["leads"][3] >= 0) == (d["leads"][1] >= 0)]
sw = sum(1 for d in surv if (d["leads"][3] >= 0) == d["up_win"])
flipped = [d for d in early if d["leads"].get(3) is not None and (d["leads"][3] >= 0) != (d["leads"][1] >= 0)]
print(f"  WAIT->min3 (signal persisted)      win%={sw/len(surv)*100 if surv else 0:.1f}%  (survivors n={len(surv)}, "
      f"{len(surv)/len(early)*100:.0f}% of early)")
print(f"  early signals that FLIPPED by min3: n={len(flipped)} ({len(flipped)/len(early)*100:.0f}%) "
      f"-> committing early buys these losers")
# of the early-committers that won, how many would the wait have kept?
print("\n=== net read: does waiting filter losers or just shrink sample? ===")
ec_loss = [d for d in early if (d["leads"][1] >= 0) != d["up_win"]]
ec_loss_persist = [d for d in ec_loss if d["leads"].get(3) is not None and abs(d["leads"][3]) >= LEAD and (d["leads"][3] >= 0) == (d["leads"][1] >= 0)]
print(f"  early-commit LOSERS: {len(ec_loss)} | of those, still-qualify@min3 (wait won't save): {len(ec_loss_persist)} "
      f"({len(ec_loss_persist)/len(ec_loss)*100 if ec_loss else 0:.0f}%)")
print("\nNOTE: binance-resolution proxy; win% only (price cost of waiting = part 2, needs PM price).")
