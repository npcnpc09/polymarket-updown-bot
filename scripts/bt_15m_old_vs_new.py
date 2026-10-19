"""bt_15m_old_vs_new.py — head-to-head backtest of OLD (early_maker: lead>=5, early multi-checkpoint,
post@bid, skip>=0.85, flat 5sh) vs NEW (z-maker: z>=2.5 & |lead|>=8 & maxlead>=15, LATE>55%, post bid+1c,
trade up to 0.95, 20sh cell @0.90-0.95) on the SAME real 15m windows.
Data: updown_tokens.jsonl (real token ids) + binance 1m klines (lead/vol signal) + PM prices-history
(real entry price + real resolution). IDENTICAL fill model both sides (assume maker fill — 15m DRY shows
~100% fill) -> RELATIVE comparison is the valid output; absolute PnL is optimistic (fill-model caveat)."""
import json, math, sys, httpx, statistics as st
from concurrent.futures import ThreadPoolExecutor
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
BSYM = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
NPER = int(sys.argv[1]) if len(sys.argv) > 1 else 400

# load real 15m token windows
wins = []
for ln in open(ROOT + "/data/updown_tokens.jsonl", encoding="utf-8"):
    try: r = json.loads(ln)
    except: continue
    if r.get("dur") == 900 and r.get("coin") in BSYM:
        wins.append(r)
wins = sorted(wins, key=lambda r: r["start"])[-NPER:]
print(f"loaded {len(wins)} real 15m windows ({BSYM.keys()})")

def bn(sym, t0, t1):
    out = {}
    try:
        r = httpx.get("https://api.binance.com/api/v3/klines",
                      params={"symbol": sym, "interval": "1m", "startTime": t0*1000, "endTime": t1*1000, "limit": 1000},
                      timeout=20).json()
        for k in r:
            if isinstance(k, list): out[int(k[0]//1000)] = (float(k[1]), float(k[4]))  # (open, close)
    except: pass
    return out

def ph(tok, st, du):
    try:
        r = httpx.get("https://clob.polymarket.com/prices-history",
                      params={"market": tok, "startTs": st-120, "endTs": st+du+180, "fidelity": "1"}, timeout=15).json()
        h = r.get("history", []) if isinstance(r, dict) else []
        return {int(x["t"]//60): float(x["p"]) for x in h}
    except: return {}

def job(w):
    coin, st_, settle, up = w["coin"], w["start"], w["settle"], w["up"]
    bnd = bn(BSYM[coin], st_-1860, settle+120)
    if st_ not in bnd: return None
    op = bnd[st_][0]
    h = ph(up, st_, 900)
    if len(h) < 5: return None
    m0 = st_//60
    # real resolution: final PM up-price >= 0.5
    last_m = max(h); up_win = h[last_m] >= 0.5
    # per-minute lead + a price getter
    def lead_at(off):  # off sec from start
        m = (st_+off)//60
        c = bnd.get(m*60)
        return math.log(c[1]/op)*1e4 if c else None
    def vol_at(off):  # pstdev of 30 prior 1m log-rets in bps
        m = (st_+off)//60
        cl = [bnd[(m-i)*60][1] for i in range(31) if (m-i)*60 in bnd]
        if len(cl) < 20: return None
        cl = cl[::-1]
        rets = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]
        return st.pstdev(rets)
    def price_at(off):
        m = (st_+off)//60
        for d in range(0, 4):
            if m-d in h: return h[m-d]
        return None
    def peak_lead(off):
        pk = 0.0
        for o in range(0, off+1, 60):
            l = lead_at(o)
            if l is not None: pk = max(pk, abs(l))
        return pk
    def fills_pullback(B, post_off):
        # maker BUY at B fills only if PM price later dips to <= B (a real pullback/reversal touches it)
        for m in range(int((st_+post_off)//60), last_m+1):
            if m in h and h[m] <= B: return True
        return False

    res = {"coin": coin, "up_win": up_win, "old": [], "new": None}

    # ---- OLD: lead>=5 at checkpoints [90,180,270,360]s, post@bid(~price), skip>=0.85, 5sh, scale-in ----
    for cp in (90, 180, 270, 360):
        l = lead_at(cp)
        if l is None or abs(l) < 5.0: continue
        side_up = l >= 0
        p = price_at(cp)
        if p is None: continue
        B = round(min(p, 0.97), 2)               # post at ~bid (mid proxy)
        if B >= 0.85: continue                    # OLD PRICE_CAP
        won = (side_up == up_win)
        res["old"].append({"B": B, "won": won, "side_up": side_up, "fill": fills_pullback(B, cp)})

    # ---- NEW: LATE (>55% => off>=495s), z>=2.5 & |lead|>=8 & maxlead>=15, post bid+1c, 0.30<=B<=0.95, cell ----
    for off in range(495, 840, 15):               # scan late window for first qualifying entry
        l = lead_at(off)
        if l is None or abs(l) < 8.0: continue
        v = vol_at(off)
        if not v: continue
        z = abs(l)/v
        if z < 2.5: continue
        if peak_lead(off) < 15.0: continue
        side_up = l >= 0
        p = price_at(off)
        if p is None: continue
        B = round(min(p+0.01, 0.97), 2)           # NEW posts bid+1c
        if not (0.30 <= B <= 0.95): continue
        sh = 20 if (0.90 <= B < 0.95) else 5
        won = (side_up == up_win)
        res["new"] = {"B": B, "won": won, "sh": sh, "z": round(z, 2), "lead": round(l, 1), "fill": fills_pullback(B, off)}
        break
    return res

data = []
with ThreadPoolExecutor(max_workers=12) as ex:
    for i, r in enumerate(ex.map(job, wins)):
        if r: data.append(r)
        if i % 100 == 0: print(f"  {i}/{len(wins)}")
print(f"usable windows: {len(data)}")

def report(label, fills, sh_field=None):
    # fills: list of dicts with B, won, optional sh
    if not fills:
        print(f"  {label:14s} (no fills)"); return
    n = len(fills)
    w = sum(1 for f in fills if f["won"])
    def shz(f): return f.get("sh", 5) if sh_field else 5
    pnl = sum(((1-f["B"]) if f["won"] else -f["B"]) * shz(f) for f in fills)
    cost = sum(f["B"]*shz(f) for f in fills)
    avgB = sum(f["B"] for f in fills)/n
    print(f"  {label:14s} fills={n:<4d} win%={w/n*100:4.0f}%  avgEntry={avgB:.3f}  "
          f"PnL=${pnl:+7.2f}  EV/fill=${pnl/n:+.3f}  margin={pnl/cost*100 if cost else 0:+.1f}%")

old_fills = [f for r in data for f in r["old"]]
new_fills = [r["new"] for r in data if r["new"]]
n_old_win = len(set(id(r) for r in data if r["old"]))
n_new_win = len(new_fills)

print("\n=== 15m HEAD-TO-HEAD (same real windows, identical assume-fill model) ===")
print(f"  windows where OLD traded: {sum(1 for r in data if r['old'])}/{len(data)}  "
      f"| windows where NEW traded: {n_new_win}/{len(data)}")
print("\n  -- equal 5sh basis (apples-to-apples per-fill) --")
report("OLD (lead>=5)", old_fills)
report("NEW (z>=2.5)", [{"B": f["B"], "won": f["won"]} for f in new_fills])
print("\n  -- NEW with real cell sizing (5/20sh) --")
report("NEW (cell)", new_fills, sh_field="sh")
# zone breakdown
print("\n  -- NEW entry-zone breakdown (where its edge lives) --")
for lo, hi in ((0.30,0.85),(0.85,0.90),(0.90,0.95)):
    z = [f for f in new_fills if lo <= f["B"] < hi]
    if z:
        wn = sum(1 for f in z if f["won"])
        pnl = sum(((1-f["B"]) if f["won"] else -f["B"])*f["sh"] for f in z)
        print(f"     [{lo:.2f}-{hi:.2f}): n={len(z):<3d} win%={wn/len(z)*100:3.0f}% PnL(cell)=${pnl:+.2f}")
print("\n=== PULLBACK-FILL model (bid fills only if price dips to it = adverse-selection-aware) ===")
old_pf = [f for f in old_fills if f.get("fill")]
new_pf = [f for f in new_fills if f.get("fill")]
print(f"  OLD fill-rate: {len(old_pf)}/{len(old_fills)} ({len(old_pf)/len(old_fills)*100:.0f}%)  "
      f"| NEW fill-rate: {len(new_pf)}/{len(new_fills)} ({len(new_pf)/len(new_fills)*100:.0f}%)")
report("OLD (pullback)", [{"B": f["B"], "won": f["won"]} for f in old_pf])
report("NEW (pullback)", new_pf, sh_field="sh")
print("\n  NOTE: assume-fill model (top block) is OPTIMISTIC and over-credits OLD's cheap early bids "
      "(they fill in reality only on a reversal = the loser). Pullback-fill is closer to the adverse-"
      "selection truth. Real anchors: OLD live 15m +$36.80/43 (+$0.86/fill); NEW = the 5m cell live "
      "(97% win, +$40+) validating the 94%-win selection profile.")
