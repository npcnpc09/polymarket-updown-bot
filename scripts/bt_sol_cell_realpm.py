"""bt_sol_cell_realpm.py — REAL-PM backtest of SOL's cell band (decisive vs the n=26 live).
1734 SOL 5m windows (06-02~08). binance SOLUSDT signal (late min3-4, |lead|>=8, z=|lead|/own_vol30>=2.5)
+ REAL PM prices-history (entry price + real resolution). Question: is SOL's REAL win% in the 0.90-0.95
cell band >=94% (live 88.5% = noise) or <94% (structurally -EV -> stop)? Also runs btc as same-method ref."""
import json, math, sys, httpx, statistics as st
from concurrent.futures import ThreadPoolExecutor
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
COINS = {"sol": "SOLUSDT", "btc": "BTCUSDT"}
toks = {c: [] for c in COINS}
for ln in open(ROOT+"/data/updown_tokens.jsonl", encoding="utf-8"):
    try: r = json.loads(ln)
    except: continue
    if r.get("dur") == 300 and r.get("coin") in COINS: toks[r["coin"]].append(r)
SER = {}
def fetch(sym, t0, t1):
    out = {}; cur = t0
    with httpx.Client() as c:
        while cur < t1:
            r = c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
            if not isinstance(r, list) or not r: break
            for k in r: out[int(k[0]//1000)] = (float(k[1]), float(k[4]))
            cur = int(r[-1][0]//1000)+60
    return out
def ph(tok, st_):
    try:
        r = httpx.get("https://clob.polymarket.com/prices-history", params={"market": tok, "startTs": st_-120, "endTs": st_+300+150, "fidelity": "1"}, timeout=15).json()
        h = r.get("history", []) if isinstance(r, dict) else []
        return {int(x["t"]//60): float(x["p"]) for x in h}
    except: return {}
def analyze(coin):
    ws_list = sorted(toks[coin], key=lambda r: r["start"])
    t0 = ws_list[0]["start"]-1860; t1 = ws_list[-1]["start"]+460
    ser = SER[coin]
    def job(r):
        st_ = r["start"]; up = r["up"]
        if st_ not in ser: return None
        o = ser[st_][0]
        h = ph(up, st_)
        if len(h) < 5: return None
        m0 = st_//60; up_win = h[max(h)] >= 0.5
        for m in (3, 4):
            c = ser.get(st_+m*60)
            if not c: continue
            lead = math.log(c[1]/o)*1e4
            if abs(lead) < 8: continue
            cl = [ser[(m0+m-i)*60][1] for i in range(31) if (m0+m-i)*60 in ser]
            if len(cl) < 20: break
            cl = cl[::-1]; rets = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]; v = st.pstdev(rets)
            if not v or abs(lead)/v < 2.5: continue
            side_up = lead >= 0
            pm = None
            for d in range(0, 3):
                if (m0+m-d) in h: pm = h[m0+m-d]; break
            if pm is None: continue
            B = pm if side_up else (1-pm)   # favorite price for our side
            won = (side_up == up_win)
            return {"B": B, "won": won}
        return None
    out = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for r in ex.map(job, ws_list):
            if r: out.append(r)
    return out

print("fetching binance...")
for c, s in COINS.items():
    wl = sorted(toks[c], key=lambda r: r["start"]); SER[c] = fetch(s, wl[0]["start"]-1860, wl[-1]["start"]+460)
    print(f"  {c}: {len(SER[c])} min, {len(toks[c])} windows")
for coin in COINS:
    print(f"\n=== {coin.upper()} real-PM (late z>=2.5 entries) ===")
    data = analyze(coin)
    cell = [d for d in data if 0.90 <= d["B"] < 0.95]
    allf = data
    def rep(rows, lab):
        if not rows: print(f"  {lab}: n=0"); return
        n = len(rows); w = sum(1 for d in rows if d["won"]); ab = sum(d["B"] for d in rows)/n
        ev = sum(((1-d["B"]) if d["won"] else -d["B"]) for d in rows)/n*5  # 5sh EV
        print(f"  {lab:16s} n={n:4d} win%={w/n*100:5.2f} avgB={ab:.3f} EV/fill(5sh)=${ev:+.3f} | breakeven win%={ab*100:.0f}")
    rep(allf, "all z>=2.5")
    rep(cell, "CELL 0.90-0.95")
    rep([d for d in data if d["B"] >= 0.95], "0.95+")
print("\nVERDICT: if SOL CELL real win% >=94% -> live 88.5%/26 was small-sample noise, SOL maker viable.")
print("If SOL CELL <94% (below its breakeven) and < btc -> structurally -EV, the live result is real, stop.")
