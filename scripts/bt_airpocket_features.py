"""bt_airpocket_features.py — QUANT analysis: are cell air-pockets identifiable at ENTRY?
30d btc+eth. Cell-eligible = late (min3-4) first-qualifying lead>=8 & z>=2.5 (the live cell signal).
Rich entry features: entry_lead, peak, persist(=|lead|/peak), toward_slope (lead momentum in our dir at
entry), accel (lead[m]-lead[1]), retrace (peak-|lead|), vol30. Settle: settle_bps, won.
DECOMPOSE losses: tight-call (|settle|<5bps, oracle-noise, IRREDUCIBLE) vs reversal (|settle|>=5bps, the
favorite clearly flipped — maybe has a signature). Then for each candidate filter: losses-avoided vs
winners-sacrificed (precision/recall) — the only honest test of 'can we identify them'."""
import math, time, statistics as st, httpx
SYMS = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
now = int(time.time()); t1 = now//60*60; t0 = t1 - 30*86400 - 2400
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
print("fetching 30d btc+eth...")
SER = {c: fetch(s) for c, s in SYMS.items()}

E = []  # cell-eligible entries with features + outcome
for coin in SYMS:
    ser = SER[coin]; ws = (t0+2400)//300*300
    while ws+300 <= t1:
        op = ser.get(ws); cl4 = ser.get(ws+240)
        if not op or not cl4: ws += 300; continue
        o = op[0]
        leads = {m: (math.log(ser[ws+m*60][1]/o)*1e4 if ser.get(ws+m*60) else None) for m in range(0, 5)}
        settle = math.log(ser[ws+240][1]/o)*1e4; up_win = settle >= 0
        for m in range(3, 5):  # late entry
            l = leads.get(m)
            if l is None or abs(l) < 8: continue
            m0 = ws+m*60; cl = [ser[m0-i*60][1] for i in range(31) if (m0-i*60) in ser]
            if len(cl) < 20: break
            cl = cl[::-1]; rets = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]; v = st.pstdev(rets)
            if not v or abs(l)/v < 2.5: continue
            peak = max(abs(leads[k]) for k in range(0, m+1) if leads.get(k) is not None)
            prev = leads.get(m-1)
            sgn = 1 if l >= 0 else -1
            toward_slope = (l-prev)*sgn if prev is not None else 0.0   # >0 = lead still growing our way
            accel = (l-leads[1])*sgn if leads.get(1) is not None else 0.0
            won = ((l >= 0) == up_win)
            E.append({"coin": coin, "lead": abs(l), "peak": peak, "persist": abs(l)/peak if peak else 1,
                      "slope": toward_slope, "accel": accel, "retrace": peak-abs(l), "vol": v, "z": abs(l)/v,
                      "won": won, "settle": abs(settle)})
            break
        ws += 300
n = len(E); wins = [e for e in E if e["won"]]; loss = [e for e in E if not e["won"]]
print(f"\ncell-eligible entries: {n} | win {len(wins)} ({len(wins)/n*100:.1f}%) | loss {len(loss)}")

# DECOMPOSE losses
tight = [e for e in loss if e["settle"] < 5]; rev = [e for e in loss if e["settle"] >= 5]
print(f"\n=== loss decomposition ===")
print(f"  tight-call (|settle|<5bps, IRREDUCIBLE oracle/coinflip): {len(tight)} ({len(tight)/len(loss)*100:.0f}% of losses)")
print(f"  clear-reversal (|settle|>=5bps, maybe identifiable):     {len(rev)} ({len(rev)/len(loss)*100:.0f}% of losses)")

def dist(rows, k):
    vs = [r[k] for r in rows]; return f"{st.median(vs):5.2f} [{st.quantiles(vs,n=4)[0]:.1f},{st.quantiles(vs,n=4)[2]:.1f}]" if len(vs)>3 else f"{st.median(vs):.2f}"
print(f"\n=== feature: WINNERS vs clear-REVERSAL losers (median [q1,q3]) ===")
print(f"  {'feat':9s} {'WIN':22s} {'REVERSAL-LOSS':22s}")
for k in ("lead","peak","persist","slope","accel","retrace","vol"):
    print(f"  {k:9s} {dist(wins,k):22s} {dist(rev,k):22s}")

# precision/recall for candidate filters (only reversal losses are 'catchable')
print(f"\n=== candidate filters: would-cut analysis (losses avoided vs winners sacrificed) ===")
def pr(pred, label):
    cl = [e for e in loss if pred(e)]; cw = [e for e in wins if pred(e)]
    tl = [e for e in tight if pred(e)]; rl = [e for e in rev if pred(e)]
    if not cl and not cw: print(f"  {label:28s} cuts nothing"); return
    cut = len(cl)+len(cw)
    print(f"  {label:28s} cut {cut:4d} ({len(cw)} WIN + {len(cl)} LOSS [{len(rl)}rev/{len(tl)}tight]) | "
          f"loss-precision {len(cl)/cut*100:4.1f}% (base {len(loss)/n*100:.1f}%) | catches {len(rl)}/{len(rev)} reversals")
pr(lambda e: e["persist"] < 0.6, "persist<0.6 (retraced)")
pr(lambda e: e["persist"] < 0.8, "persist<0.8")
pr(lambda e: e["slope"] < 0, "slope<0 (lead fading at entry)")
pr(lambda e: e["slope"] < -1, "slope<-1 (clearly fading)")
pr(lambda e: e["lead"] < 10, "lead<10 (weak)")
pr(lambda e: e["peak"] < 12, "peak<12 (weak peak)")
pr(lambda e: e["accel"] > 20, "accel>20 (climax-ish)")
pr(lambda e: e["retrace"] > 8, "retrace>8 (far off peak)")
pr(lambda e: e["persist"] < 0.7 and e["slope"] < 0, "persist<0.7 AND slope<0")
print(f"\nREAD: a filter is useful only if loss-precision >> base AND it catches a big share of reversals "
      "WITHOUT cutting many winners. tight-call losses are uncatchable by entry features (settle~0).")
