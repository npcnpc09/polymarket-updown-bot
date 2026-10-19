"""climax_week_backtest.py — 7-day SIGNAL-LEVEL backtest of the z-maker entry (z>=2.5 & |lead|>=6,
entry window [165s,275s] of each 5m, btc/eth) comparing the CLIMAX SKIP (|lead|>=30 & accel>=20)
deployed 2026-06-10 vs baseline. Reconstructs binance 1s lead paths + 1m vol30 exactly like the
live engine (bin_vol30 = pstdev of 30 1m log-returns in bps).

HONEST SCOPE: signal-level (assumes the maker order fills) — absolute EV is NOT trustworthy
(fill-model trap); the CLIMAX vs KEEP comparison shares the same bias on both arms and is the
question this answers. Settle = binance close vs open (Chainlink mismatch matters only in ties;
ties <3bps reported separately). EV estimate uses the LIVE-calibrated price B per |lead| bucket."""
import json, math, time, statistics, sys
import httpx

COINS = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
DAYS = 7
THR_BPS = 6.0; ENTRY_Z = 2.5; T0, T1 = 165, 275   # LATE_FRAC*300, settle-MIN_TTL
CLIMAX_LEAD, CLIMAX_ACCEL = 30.0, 20.0
LEAD_EARLY_T = 5                                   # engine sets lead_early at first sampler tick (<90s)

now = int(time.time())
week_start = (now - DAYS * 86400) // 300 * 300

cli = httpx.Client(timeout=20)

def klines(sym, interval, start_ms, end_ms, limit=1000):
    for attempt in range(5):
        try:
            r = cli.get("https://api.binance.com/api/v3/klines",
                        params={"symbol": sym, "interval": interval, "startTime": start_ms,
                                "endTime": end_ms, "limit": limit})
            if r.status_code == 429:
                time.sleep(30); continue
            return r.json()
        except Exception:
            time.sleep(3)
    return []

def fetch_1m(sym, start, end):
    """minute ts -> (open, close), covering [start-1860, end]"""
    out = {}
    t = (start - 1860) * 1000
    while t < end * 1000:
        ks = klines(sym, "1m", t, end * 1000)
        if not ks: break
        for k in ks: out[k[0] // 1000] = (float(k[1]), float(k[4]))
        t = ks[-1][0] + 60000
        time.sleep(0.15)
    return out

def fetch_1s_day(sym, day_start):
    """second ts -> close for one day"""
    out = {}
    t = day_start * 1000; end = (day_start + 86400) * 1000
    while t < end:
        ks = klines(sym, "1s", t, end - 1)
        if not ks: break
        for k in ks: out[k[0] // 1000] = float(k[4])
        t = ks[-1][0] + 1000
        time.sleep(0.12)
    return out

def px_at(sec_map, t):
    for d in range(6):                  # forward-fill small gaps
        if t - d in sec_map: return sec_map[t - d]
    return None

# live-calibrated avg maker price B per |lead|-at-entry bucket (from multi_window_engine_live.jsonl z-era)
live = [json.loads(l) for l in open(r"data\multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()]
lv = [r for r in live if r.get("zscore") is not None]
def lead_bucket(x):
    x = abs(x)
    return "6-12" if x < 12 else "12-18" if x < 18 else "18-30" if x < 30 else "30+"
bmap = {}
for b in ("6-12", "12-18", "18-30", "30+"):
    rs = [r["B"] for r in lv if lead_bucket(r["lead"]) == b]
    bmap[b] = statistics.mean(rs) if rs else 0.85
print("live-calibrated B by |lead| bucket:", {k: round(v, 3) for k, v in bmap.items()})

entries = []
for coin, sym in COINS.items():
    m1 = fetch_1m(sym, week_start, now)
    print(f"{coin}: {len(m1)} 1m candles fetched", flush=True)
    for d in range(DAYS):
        day_start = week_start + d * 86400
        s1 = fetch_1s_day(sym, day_start)
        if not s1:
            print(f"{coin} day {d}: no 1s data"); continue
        for wstart in range(day_start, day_start + 86400, 300):
            if wstart + 300 > now - 60: break
            op = m1.get(wstart, (None,))[0]
            if op is None: continue
            # vol30 at entry-eval time: pstdev of 30 1m log-returns ending at the minute before T0
            vt = (wstart + T0) // 60 * 60
            cl = [m1[vt - i * 60][1] for i in range(31, 0, -1) if (vt - i * 60) in m1]
            if len(cl) < 25: continue
            vol = statistics.pstdev([math.log(cl[i] / cl[i - 1]) * 1e4 for i in range(1, len(cl))])
            if not vol: continue
            pe = px_at(s1, wstart + LEAD_EARLY_T)
            lead_early = math.log(pe / op) * 1e4 if pe else None
            ent = None
            for t in range(T0, T1 + 1, 2):           # engine ticks ~2s
                p = px_at(s1, wstart + t)
                if p is None: continue
                lead = math.log(p / op) * 1e4
                if abs(lead) < THR_BPS: continue
                if abs(lead) / vol < ENTRY_Z: continue
                accel = (lead - lead_early) * (1 if lead >= 0 else -1) if lead_early is not None else None
                ent = (t, lead, accel); break
            if ent is None: continue
            t, lead, accel = ent
            pc = px_at(s1, wstart + 299)
            if pc is None: continue
            settle_lead = math.log(pc / op) * 1e4
            side_up = lead >= 0
            won = (settle_lead > 0) == side_up
            B = bmap[lead_bucket(lead)]
            pnl = ((1 - B) if won else -B) * 5
            entries.append({"coin": coin, "day": time.strftime("%m-%d", time.gmtime(wstart)),
                            "t": t, "lead": round(lead, 1), "accel": round(accel, 1) if accel is not None else None,
                            "vol": round(vol, 1), "won": won, "tie": abs(settle_lead) < 3, "est_pnl": round(pnl, 2),
                            "climax": (accel is not None and abs(lead) >= CLIMAX_LEAD and accel >= CLIMAX_ACCEL)})
        print(f"{coin} {time.strftime('%m-%d', time.gmtime(day_start))}: entries so far {len(entries)}", flush=True)

json.dump(entries, open(r"data\climax_week_backtest.json", "w"))
print(f"\nTOTAL simulated z-entries: {len(entries)}")

def rep(rows, label):
    n = len(rows)
    if not n: print(f"  {label:<22} n=0"); return
    w = sum(r["won"] for r in rows)
    p = sum(r["est_pnl"] for r in rows)
    print(f"  {label:<22} n={n:<5} win={w/n:>5.1%}  est_pnl={p:+9.2f}  ev/trade={p/n:+.3f}")

for tie_excl in (False, True):
    rows = [r for r in entries if not (tie_excl and r["tie"])]
    print(f"\n===== {'EXCLUDING' if tie_excl else 'INCLUDING'} ties(<3bps) n={len(rows)} =====")
    rep(rows, "baseline (all)")
    rep([r for r in rows if not r["climax"]], "KEEP (post-change)")
    rep([r for r in rows if r["climax"]], "CLIMAX (cut)")
    print("  per-day:")
    days = sorted({r["day"] for r in rows})
    for dd in days:
        rs = [r for r in rows if r["day"] == dd]
        cx = [r for r in rs if r["climax"]]; kp = [r for r in rs if not r["climax"]]
        cw = f"{sum(r['won'] for r in cx)}/{len(cx)}" if cx else "0/0"
        print(f"    {dd}: all n={len(rs):<4} win={sum(r['won'] for r in rs)/len(rs):>5.1%} | "
              f"keep n={len(kp):<4} win={(sum(r['won'] for r in kp)/len(kp)) if kp else 0:>5.1%} "
              f"ev={sum(r['est_pnl'] for r in kp)/len(kp) if kp else 0:+.3f} | "
              f"climax {cw} pnl_cut={sum(r['est_pnl'] for r in cx):+7.2f}")
