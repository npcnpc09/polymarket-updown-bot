"""twoside_live.py — MICRO real-money probe of the day-split-validated 1h two-sided cheap-maker
(0xb55f rule C: 1h windows, accumulate BOTH sides ONLY when best_bid<=0.50; matched pairs<$1 lock
profit at settle, half-legs are cheap lottery). Reverse-engineered + validated on his 64k real fills
(FIT +4.6% / HOLDOUT +6.4%) and on twoside_dry v3 (STRICT +24% / 28h). Purpose: measure the DRY->live
EXECUTION DISCOUNT — the one number no paper model can give.

HARD SAFETY CAPS (real money on a compromised wallet — capital preservation first):
  1h btc/eth only; CLIP 5sh; MAX_SH 15/side/window; MAX_EXPOSURE $40; DAILY_STOP -$8; MAX_ORDERS 60/day.
  post_only=True (pure maker — reject if it would cross to taker). Hold to settle, NEVER sell.
  One live resting order per (window,side); re-quote only if bid moved >=1c (cancel-then-replace,
  one-shot guard prevents the 2026-07-02 stacking bug). DRY default; --place = REAL.

Real PnL = WALLET (wallet_log), not this file's binance-graded tally (tight calls noisy). -> data/twoside_live.jsonl
"""
import asyncio, json, time, signal, sys, os, math, datetime
from datetime import timezone, timedelta
import httpx
for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except: pass
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACE = ("--place" in sys.argv)
COINS = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
GAMMA = "https://gamma-api.polymarket.com/markets"
WORDC = {"btc": "bitcoin", "eth": "ethereum"}
ET = timezone(timedelta(hours=-4))
DUR = 3600
CLIP = 5                 # shares per order (platform min)
MAX_SH = 15              # per side per window
FAV_CAP = 0.50           # only accumulate the validated cheap band
PAIR_CAP = 0.98          # quote 2nd side only if pair cost stays <= this
MAX_EXPOSURE = 40.0      # $ across all open filled shares
DAILY_STOP = -8.0        # realized-pnl halt for the UTC day
MAX_ORDERS = 60          # total placements/day backstop
OPEN_UNTIL = 0.80        # stop opening new resting orders after 80% of window elapsed
OUTF = os.path.join(ROOT, "data", "twoside_live.jsonl")
LOG = os.path.join(ROOT, "data", "twoside_live.log")
_run = True
def _sig(*_):
    global _run; _run = False
signal.signal(signal.SIGINT, _sig)
def now(): return time.time()
def uday(): return datetime.datetime.utcnow().strftime("%Y-%m-%d")
def log(m):
    line = f"[{datetime.datetime.utcnow().strftime('%m-%d %H:%M:%S')}] {m}"; print(line, flush=True)
    try: open(LOG, "a", encoding="utf-8").write(line + "\n")
    except: pass
def load_env():
    for l in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        if "=" in l and not l.startswith("#"):
            k, v = l.strip().split("=", 1); os.environ.setdefault(k.strip(), v.strip())
    return os.environ["POLY_PK"], os.environ["POLY_PROXY"]
def trader():
    pk, proxy = load_env(); from polymarket import SecureClient
    return SecureClient.create(private_key=pk, wallet=proxy)
def slug_1h(coin, ws):
    d = datetime.datetime.fromtimestamp(ws, tz=ET)
    h12 = d.hour % 12 or 12; ap = "pm" if d.hour >= 12 else "am"
    return f"{WORDC[coin]}-up-or-down-{d.strftime('%B').lower()}-{d.day}-{d.year}-{h12}{ap}-et"
async def toks(c, slug):
    try:
        arr = (await c.get(GAMMA, params={"slug": slug}, timeout=10)).json()
        if arr:
            ids = json.loads(arr[0]["clobTokenIds"]); outs = json.loads(arr[0]["outcomes"])
            return ids[outs.index("Up")], ids[outs.index("Down")]
    except: pass
    return None, None
async def bestbid(c, tok):
    try:
        b = (await c.get("https://clob.polymarket.com/book", params={"token_id": tok}, timeout=8)).json()
        bids = [float(x["price"]) for x in b.get("bids", []) if float(x["size"]) > 0 and 0 < float(x["price"]) < 1]
        return max(bids) if bids else None
    except: return None
async def bopen(c, sym, st_):
    try:
        k = (await c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "startTime": st_ * 1000, "limit": 1}, timeout=8)).json()
        return float(k[0][1])
    except: return None
async def klc(c, sym, st_):
    try:
        k = (await c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "startTime": (st_ + DUR) * 1000 - 60000, "limit": 1}, timeout=8)).json()
        return float(k[0][4])
    except: return None

def quote_for(bb, my_sz, other_avg, other_sz):
    if bb is None or my_sz >= MAX_SH: return None
    q = math.floor(bb * 100) / 100
    q = min(q, FAV_CAP)
    if other_sz > 0 and other_avg is not None:
        q = min(q, math.floor((PAIR_CAP - other_avg) * 100) / 100)
    return q if q >= 0.01 else None

async def main():
    cli = None; proxy = None
    realized = {}     # uday -> pnl
    orders_today = {} # uday -> count
    halted = set()    # udays that hit stop
    W = {}
    if PLACE:
        cli = trader(); proxy = os.environ.get("POLY_PROXY")
        try:
            bal = float(cli.get_balance_allowance(asset_type="COLLATERAL").balance) / 1e6
            log(f"LIVE wallet ${bal:.2f}")
        except Exception as e: log(f"bal err {str(e)[:60]}")
    async with httpx.AsyncClient() as c:
        log(f"twoside_live START [{'LIVE --place' if PLACE else 'DRY'}] 1h {list(COINS)} clip{CLIP} maxsh{MAX_SH} cap{FAV_CAP} exp${MAX_EXPOSURE} stop${DAILY_STOP}")
        while _run:
            t = now(); ws = int(t // DUR) * DUR; d = uday()
            realized.setdefault(d, 0.0); orders_today.setdefault(d, 0)
            # discover current-hour windows
            for coin, sym in COINS.items():
                slug = slug_1h(coin, ws)
                if slug in W: continue
                up, dn = await toks(c, slug)
                if not up: continue
                op = await bopen(c, sym, ws)
                W[slug] = {"slug": slug, "coin": coin, "sym": sym, "ws": ws, "open": op, "tok_up": up, "tok_dn": dn,
                           "done": False, "up": _leg(), "dn": _leg()}
                log(f"[{slug}] TRACK open={op}")
            # exposure across open filled shares
            exposure = sum((w["up"]["usd"] + w["dn"]["usd"]) for w in W.values() if not w["done"])
            day_halt = (realized[d] <= DAILY_STOP) or (orders_today[d] >= MAX_ORDERS) or (exposure >= MAX_EXPOSURE)
            if realized[d] <= DAILY_STOP and d not in halted:
                halted.add(d); log(f"=== DAILY-STOP HALT {d} realized ${realized[d]:.2f} ===")
            # quote/fill pass
            for slug, w in list(W.items()):
                if w["done"]: continue
                sec = t - w["ws"]
                if sec <= DUR * OPEN_UNTIL and not day_halt:
                    for side in ("up", "dn"):
                        try: await quote_side(c, cli, w, side, proxy, orders_today, d)
                        except Exception as e: log(f"[{slug}] {side} quote err {str(e)[:60]}")
                # settle
                if sec > DUR + 8 and not w["done"]:
                    w["done"] = True
                    # cancel any resting unfilled
                    if PLACE and cli:
                        for side in ("up", "dn"):
                            oid = w[side].get("oid")
                            if oid and not w[side].get("order_filled"):
                                try: cli.cancel_order(order_id=oid)
                                except: pass
                    cl = await klc(c, w["sym"], w["ws"])
                    u, dd = w["up"], w["dn"]
                    if (u["sz"] or dd["sz"]) and cl and w["open"]:
                        sb = math.log(cl / w["open"]) * 1e4
                        winner = "up" if sb > 0 else "dn"
                        spend = u["usd"] + dd["usd"]; payout = (u if winner == "up" else dd)["sz"] * 1.0
                        pnl = payout - spend
                        realized[d] += pnl
                        m = min(u["sz"], dd["sz"]); pair = ((u["usd"]/u["sz"]) + (dd["usd"]/dd["sz"])) if m > 0 else None
                        rec = {"slug": slug, "coin": w["coin"], "ts": w["ws"], "settle_bps": round(sb, 1), "winner": winner,
                               "up_sz": u["sz"], "up_usd": round(u["usd"], 2), "dn_sz": dd["sz"], "dn_usd": round(dd["usd"], 2),
                               "matched": m, "pair": round(pair, 3) if pair else None,
                               "spend": round(spend, 2), "payout": round(payout, 2), "pnl": round(pnl, 2),
                               "live": PLACE, "day_realized": round(realized[d], 2)}
                        open(OUTF, "a", encoding="utf-8").write(json.dumps(rec) + "\n")
                        log(f"[{slug}] SETTLE win={winner} sbps={sb:+.0f} up{u['sz']}/dn{dd['sz']} m={m} pair={rec['pair']} pnl={pnl:+.2f} dayReal={realized[d]:+.2f}")
                    W.pop(slug, None)
            await asyncio.sleep(4)

def _leg(): return {"sz": 0, "usd": 0.0, "oid": None, "quote": None, "order_filled": False, "n_orders": 0}

async def quote_side(c, cli, w, side, proxy, orders_today, d):
    leg = w[side]; other = w["dn"] if side == "up" else w["up"]
    tok = w["tok_up"] if side == "up" else w["tok_dn"]
    bb = await bestbid(c, tok)
    other_avg = (other["usd"] / other["sz"]) if other["sz"] > 0 else None
    q = quote_for(bb, leg["sz"], other_avg, other["sz"])
    # --- DRY: model fill as best_bid crossing (STRICT-ish); real engine uses order status ---
    if not PLACE:
        leg["quote"] = q
        if q is not None and bb is not None and bb <= q and leg["sz"] < MAX_SH:
            leg["sz"] += CLIP; leg["usd"] += CLIP * q
        return
    # --- LIVE ---
    if cli is None: return
    # 1) check existing resting order for fill
    if leg["oid"] and not leg["order_filled"]:
        try:
            od = cli.get_order(order_id=leg["oid"]); mt = float(getattr(od, "size_matched", 0) or 0)
            if mt >= CLIP - 1e-6:
                leg["sz"] += CLIP; leg["usd"] += CLIP * leg["quote"]; leg["order_filled"] = True; leg["oid"] = None
                log(f"[{w['slug']}] FILL {side.upper()} {CLIP}sh @ {leg['quote']:.2f} (up={w['up']['sz']} dn={w['dn']['sz']})")
        except: pass
    # 2) if no live order and room + budget, place one (or re-quote if bid moved >=1c)
    if q is None or leg["sz"] >= MAX_SH: return
    if leg["oid"] and not leg["order_filled"]:
        if leg["quote"] is not None and abs(q - leg["quote"]) < 0.01: return  # keep resting
        try: cli.cancel_order(order_id=leg["oid"])   # bid moved -> replace
        except: pass
        leg["oid"] = None
    if leg["oid"] is None and orders_today[d] < MAX_ORDERS and leg["n_orders"] < 12:
        try:
            r = cli.place_limit_order(token_id=tok, price=q, size=CLIP, side="BUY", post_only=True)
            oid = getattr(r, "order_id", None) or getattr(r, "id", None)
            if oid:
                leg["oid"] = oid; leg["quote"] = q; leg["order_filled"] = False
                leg["n_orders"] += 1; orders_today[d] += 1
                log(f"[{w['slug']}] REST {side.upper()} {CLIP}sh @ {q:.2f} (bid={bb}) ord#{orders_today[d]}")
        except Exception as e:
            log(f"[{w['slug']}] place err {str(e)[:60]}")

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
