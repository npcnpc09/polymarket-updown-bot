"""bt_5m_strategy_regime_map.py — REAL-money differentiating map for btc/eth 5m: which strategy wins in
which regime? Uses LIVE daily PnL (no fill-model trap). z-maker (late maker/cell) vs early-taker (early
taker), per UTC day, vs that day's regime (eth/btc realized vol + efficiency ratio ER). Tests the
complementarity thesis (does taker carry some regimes, maker others?)."""
import json, re, math, time, statistics as st, httpx
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def daypnl(f, kind):
    out = {}
    for o in (json.loads(l) for l in open(ROOT+"/"+f, encoding="utf-8") if l.strip()):
        ok = (o.get("kind") == "entry") if kind == "taker" else (o.get("filled") is True)
        if ok and o.get("won") is not None and o.get("pnl") is not None:
            m = re.search(r"-5m-(\d+)", o.get("slug", ""))
            if not m: continue
            d = datetime.fromtimestamp(int(m.group(1)), timezone.utc).strftime("%m-%d")
            out.setdefault(d, [0.0, 0, 0]); out[d][0] += float(o["pnl"]); out[d][1] += 1; out[d][2] += 1 if o["won"] else 0
    return out
zm = daypnl("data/multi_window_engine_live.jsonl", "maker")
tk = daypnl("data/early_taker_probe.jsonl", "taker")
days = sorted(set(zm) | set(tk))
# regime per day: eth vol + ER (and btc vol)
t1 = int(time.time())//60*60; t0 = t1 - 18*86400
def fetch(sym):
    out = {}; cur = t0
    with httpx.Client() as c:
        while cur < t1:
            r = c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
            if not isinstance(r, list) or not r: break
            for k in r: out[int(k[0]//1000)] = (float(k[1]), float(k[4]))
            cur = int(r[-1][0]//1000)+60
    return out
print("fetching klines...")
ETH = fetch("ETHUSDT"); BTC = fetch("BTCUSDT")
def day_regime(ser, dstr):
    yr = 2026
    d0 = int(datetime.strptime(f"{yr}-{dstr}", "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    mins = [m for m in ser if d0 <= m < d0+86400]
    if len(mins) < 100: return None, None
    mins.sort(); cl = [ser[m][1] for m in mins]
    rets = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]
    vol = st.pstdev(rets)
    # ER over the day (5m windows avg efficiency)
    ers = []
    for i in range(0, len(cl)-5, 5):
        net = abs(cl[i+5]-cl[i]); path = sum(abs(cl[i+j+1]-cl[i+j]) for j in range(5))
        if path: ers.append(net/path)
    er = sum(ers)/len(ers) if ers else 0
    return vol, er
print(f"\n{'day':6s} {'ethVol':>6s} {'ER':>5s} {'regime':9s} | {'zmaker$':>9s}(n,w%) | {'taker$':>9s}(n,w%) | carried")
print("-"*92)
zt = 0.0; tt = 0.0
for d in days:
    ev, er = day_regime(ETH, d)
    if ev is None: continue
    reg = "trend" if er >= 0.42 else "chop"
    z = zm.get(d, [0, 0, 0]); t = tk.get(d, [0, 0, 0])
    zt += z[0]; tt += t[0]
    zc = f"{z[0]:+.2f}({z[1]},{z[2]/z[1]*100 if z[1] else 0:.0f}%)"
    tc = f"{t[0]:+.2f}({t[1]},{t[2]/t[1]*100 if t[1] else 0:.0f}%)"
    carried = "zmaker" if z[0] > t[0] else "taker"
    print(f"{d:6s} {ev:6.2f} {er:5.2f} {('hiVol' if ev>=7 else 'loVol')+'/'+reg:9s} | {zc:>16s} | {tc:>16s} | {carried}")
print("-"*92)
print(f"  totals: zmaker ${zt:+.2f} | taker ${tt:+.2f}")
print("\nREAD: if zmaker carries some regimes and taker others (and the loser is still ~flat), they're")
print("COMPLEMENTARY -> running both smooths PnL across regimes. If one always wins, drop the other.")
