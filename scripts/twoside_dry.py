"""twoside_dry.py — DRY probe of the 0xb55f 'Lively-Authenticity' two-sided maker strategy.

Reverse-engineered rules (from 1925 real fills / 88 windows, 2026-07-05, real settled ROI 9.5%):
  * trade EVERY crypto updown window (no entry signal): btc/eth/sol/xrp x 5m/15m
  * rest small BUY orders on BOTH sides simultaneously, passive at best_bid (clean cents)
  * tiny clips (15 sh), keep re-arming all window long -> accumulate
  * PAIR BUDGET: once one side has avg cost a, quote other side only at <= PAIR_CAP - a
    (goal: matched Up+Down pairs costing < $1 -> locked profit at settle)
  * half-legs tolerated (his median 46%), hold to settle, never sell
FILL MODEL = real trade prints (data-api /trades), dual bounds (strength_maker lesson —
passive fill models lie, so we bracket):
  STRICT: a taker SELL printed at price < our resting quote (seller went THROUGH our level
          -> we were certainly filled regardless of queue position). Lower bound.
  TOUCH : a taker SELL printed at price <= our quote (we were at the touch; queue position
          unknown -> optimistic). Upper bound.
  Truth lies between; judge the strategy on STRICT.
Settle = binance 1m close vs open (Chainlink mismatch on tight calls -> settle_bps logged,
apply coin-flip model in analysis). No orders placed, zero cost.
-> data/twoside_dry.jsonl
"""
import asyncio, json, time, math, os, sys
from datetime import datetime, timezone, timedelta
import httpx
for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except: pass
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTF = os.path.join(ROOT, "data", "twoside_dry.jsonl")
LOG = os.path.join(ROOT, "data", "twoside_dry.log")
GAMMA = "https://gamma-api.polymarket.com/markets"
COINS = {"btc": "BTCUSDT", "eth": "ETHUSDT", "sol": "SOLUSDT", "xrp": "XRPUSDT"}
DURS = {"1h": 3600}  # v3: 1h ONLY — day-split-validated on HIS real fills (rule C: 1h+p<=0.5
                     # FIT +4.6% / HOLDOUT +6.4% / cf +3032; 5m/15m cheap tails are bleeds)
CLIP = 15          # shares per fill event (his median fill 15 sh)
MAX_SH = 90        # per-side cap per window
PAIR_CAP = 0.98    # quote other side only if pair cost stays <= this
FAV_CAP = 0.50     # v3: only accumulate the CHEAP side (<=0.5) — the validated profit band
WORDC = {"btc": "bitcoin", "eth": "ethereum", "sol": "solana", "xrp": "xrp"}
ET = timezone(timedelta(hours=-4))  # EDT (summer)
def slug_1h(coin, ws):
    d = datetime.fromtimestamp(ws, tz=ET)
    h12 = d.hour % 12 or 12; ap = "pm" if d.hour >= 12 else "am"
    return f"{WORDC[coin]}-up-or-down-{d.strftime('%B').lower()}-{d.day}-{d.year}-{h12}{ap}-et"
POLL = 4           # seconds between book polls
def now(): return time.time()
def log(m):
    line = f"[{time.strftime('%H:%M:%S', time.gmtime())}] {m}"; print(line, flush=True)
    try: open(LOG, "a", encoding="utf-8").write(line + "\n")
    except: pass

async def bopen(c, sym, st_):
    try:
        k = (await c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "startTime": st_ * 1000, "limit": 1}, timeout=8)).json()
        return float(k[0][1])
    except: return None
async def klc(c, sym, st_, off):
    try:
        k = (await c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "startTime": (st_ + off) * 1000, "limit": 1}, timeout=8)).json()
        return float(k[0][4])
    except: return None
async def toks(c, slug):
    try:
        arr = (await c.get(GAMMA, params={"slug": slug}, timeout=10)).json()
        if arr:
            ids = json.loads(arr[0]["clobTokenIds"]); outs = json.loads(arr[0]["outcomes"])
            return ids[outs.index("Up")], ids[outs.index("Down")], arr[0].get("conditionId")
    except: pass
    return None, None, None
async def trades(c, cid, since_ts):
    """Recent taker prints for a market; returns list of (ts, asset, side, price, size, hash)."""
    try:
        arr = (await c.get("https://data-api.polymarket.com/trades", params={"market": cid, "limit": 100}, timeout=8)).json()
        return [(int(x["timestamp"]), x["asset"], x["side"], float(x["price"]), float(x["size"]), x.get("transactionHash", "")) for x in arr if int(x["timestamp"]) >= since_ts]
    except: return []
async def book(c, tok):
    try:
        b = (await c.get("https://clob.polymarket.com/book", params={"token_id": tok}, timeout=8)).json()
        bids = [float(x["price"]) for x in b.get("bids", []) if float(x["size"]) > 0 and 0 < float(x["price"]) < 1]
        asks = [float(x["price"]) for x in b.get("asks", []) if float(x["size"]) > 0 and 0 < float(x["price"]) < 1]
        return (max(bids) if bids else None), (min(asks) if asks else None)
    except: return None, None

W = {}  # slug -> window state
def _quote(side_avg_other, other_sz, bb):
    """Passive quote: join best bid, capped by pair budget when other side has inventory."""
    if bb is None: return None
    q = math.floor(bb * 100) / 100          # clean cent, join bid
    q = min(q, FAV_CAP)                     # v2: hard cap — no blind buys above 0.85
    if other_sz > 0 and side_avg_other is not None:
        cap = math.floor((PAIR_CAP - side_avg_other) * 100) / 100
        q = min(q, cap)
    return q if q >= 0.01 else None

async def poll_window(c, w):
    """One quoting + trade-print fill pass for one window (dual STRICT/TOUCH inventories)."""
    # 1) refresh quotes from books (quote follows bid; pair budget from STRICT inventory)
    for side in ("up", "dn"):
        tok = w["tok_" + side]
        if tok is None: continue
        bb, ba = await book(c, tok)
        if bb is None: continue
        o = w["dn"] if side == "up" else w["up"]
        avg_o = (o["s_usd"] / o["s_sz"]) if o["s_sz"] > 0 else None
        w[side]["quote"] = _quote(avg_o, o["s_sz"], bb)
    # 2) fills from real prints since last poll — ONE resting order per side per cycle:
    #    a 15sh order fills once; the re-post happens at the NEXT cycle's (moved) bid.
    prints = await trades(c, w["cid"], w.get("last_t", w["ws"]) - 1)
    newmax = w.get("last_t", w["ws"])
    s_done = {"up": False, "dn": False}; t_done = {"up": False, "dn": False}
    for ts, asset, side_, px, sz, h in prints:
        if h in w["seen"]: continue
        w["seen"].add(h); newmax = max(newmax, ts)
        if side_ != "SELL": continue                    # only taker sells hit our resting bids
        side = "up" if asset == w["tok_up"] else ("dn" if asset == w["tok_dn"] else None)
        if side is None: continue
        q = w[side]["quote"]
        if q is None: continue
        # STRICT: print went through our level
        if px < q - 1e-9 and not s_done[side] and w[side]["s_sz"] < MAX_SH:
            s_done[side] = True
            w[side]["s_sz"] += CLIP; w[side]["s_usd"] += CLIP * q
            w[side]["fills"].append({"t": int(ts - w["ws"]), "px": q, "m": "S", "print": px})
            log(f"[{w['slug']}] FILL-S {side.upper()} {CLIP}sh @ {q:.2f} (print {px:.3f}) up={w['up']['s_sz']} dn={w['dn']['s_sz']}")
        # TOUCH: print at our level
        if px <= q + 1e-9 and not t_done[side] and w[side]["t_sz"] < MAX_SH:
            t_done[side] = True
            w[side]["t_sz"] += CLIP; w[side]["t_usd"] += CLIP * q
    w["last_t"] = newmax

async def main():
    log(f"twoside_dry START coins={list(COINS)} durs={list(DURS)} clip={CLIP} maxsh={MAX_SH} paircap={PAIR_CAP} poll={POLL}s [DRY, conservative ask-cross fills]")
    async with httpx.AsyncClient() as c:
        last_disc = 0
        while True:
            t = now()
            # --- discovery (every 20s) ---
            if t - last_disc >= 20:
                last_disc = t
                for dur, dsec in DURS.items():
                    ws = int(t // dsec * dsec)
                    if t - ws > dsec * 0.85: continue      # too late in window, skip new entry
                    for coin, sym in COINS.items():
                        slug = slug_1h(coin, ws) if dur == "1h" else f"{coin}-updown-{dur}-{ws}"
                        if slug in W: continue
                        up, dn, cid = await toks(c, slug)
                        if not up or not cid: continue
                        op = await bopen(c, sym, ws)
                        W[slug] = {"slug": slug, "coin": coin, "sym": sym, "dur": dur, "dsec": dsec, "ws": ws,
                                   "open": op, "tok_up": up, "tok_dn": dn, "cid": cid, "done": False,
                                   "seen": set(), "last_t": int(t),
                                   "up": {"s_sz": 0, "s_usd": 0.0, "t_sz": 0, "t_usd": 0.0, "fills": [], "quote": None},
                                   "dn": {"s_sz": 0, "s_usd": 0.0, "t_sz": 0, "t_usd": 0.0, "fills": [], "quote": None}}
                        log(f"[{slug}] TRACK (open={op})")
            # --- quoting/fill pass on live windows ---
            live = [w for w in W.values() if not w["done"] and now() - w["ws"] <= w["dsec"]]
            for w in live:
                try: await poll_window(c, w)
                except Exception as e: log(f"[{w['slug']}] poll err {e}")
            # --- settle pass ---
            for s in list(W.keys()):
                w = W[s]
                if w["done"] or now() - w["ws"] <= w["dsec"] + 5: continue
                cl = await klc(c, w["sym"], w["ws"], w["dsec"])
                if cl is None and now() - w["ws"] < w["dsec"] + 240: continue
                w["done"] = True
                u, d = w["up"], w["dn"]
                if cl and w["open"]:
                    settle = math.log(cl / w["open"]) * 1e4
                    winner = "up" if settle > 0 else "dn"
                    def acct(pfx):
                        usz, uusd = u[pfx + "_sz"], u[pfx + "_usd"]; dsz, dusd = d[pfx + "_sz"], d[pfx + "_usd"]
                        spend = uusd + dusd; payout = (usz if winner == "up" else dsz) * 1.0
                        m = min(usz, dsz)
                        pair = ((uusd / usz) + (dusd / dsz)) if m > 0 else None
                        return usz, round(uusd, 2), dsz, round(dusd, 2), m, (round(pair, 3) if pair else None), round(spend, 2), round(payout - spend, 2)
                    su, suu, sd, sdu, sm, spair, ssp, spnl = acct("s")
                    tu, tuu, td, tdu, tm, tpair, tsp, tpnl = acct("t")
                    if su or sd or tu or td:
                        rec = {"slug": w["slug"], "coin": w["coin"], "dur": w["dur"], "ts": w["ws"],
                               "settle_bps": round(settle, 1), "winner": winner,
                               "s_up": su, "s_dn": sd, "s_matched": sm, "s_pair": spair, "s_spend": ssp, "s_pnl": spnl,
                               "t_up": tu, "t_dn": td, "t_matched": tm, "t_pair": tpair, "t_spend": tsp, "t_pnl": tpnl,
                               "fills": u["fills"] + d["fills"]}
                        open(OUTF, "a", encoding="utf-8").write(json.dumps(rec) + "\n")
                        log(f"[{s}] SETTLE win={winner} sbps={settle:+.0f} STRICT up{su}/dn{sd} m={sm} pair={spair} pnl={spnl:+.2f} | TOUCH up{tu}/dn{td} m={tm} pair={tpair} pnl={tpnl:+.2f}")
                    else:
                        log(f"[{s}] SETTLE win={winner} sbps={settle:+.0f} no fills")
                W.pop(s, None)
            await asyncio.sleep(POLL)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
