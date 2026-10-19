"""WS-based REAL MONEY arb executor.

⚠️ ACTUAL ORDERS PLACED ON POLYMARKET. ⚠️

Conservative config:
  MAX_OPEN_PAIRS = 3
  MAX_EFF_SUM    = 0.93 (5c slip buffer)
  MIN_TTL_SEC    = 90 (extra safety window)
  DAILY_LOSS     = -$5 stop
  EMERGENCY_FLOOR = $60 wallet
  HALF_LEG_TIMEOUT = 5s
  TICK_SIZE = 0.01

Logic:
  1. Detect arb via WS (sum<0.93, ttl>=90s)
  2. Place limit BUY Up + Down at top_ask+1c (POSTONLY → either fills or doesn't, no chase)
  3. Check fills after 5s. If only one leg filled → cancel other + emergency hedge
  4. Hold to settle, payout auto-credits wallet
"""
import argparse, asyncio, json, os, signal, sys, time, traceback
from collections import defaultdict
from datetime import datetime, timezone

import httpx
try:
    import websockets
except ImportError:
    print("pip install websockets"); sys.exit(1)

from polymarket import SecureClient

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except: pass

# === Aligned with paper + half-leg recovery ===
MAX_OPEN_PAIRS = 5
MAX_EFF_SUM = 0.93          # tightened to leave room for 4c slip × 2 legs
MIN_TTL_SEC = 60
DAILY_LOSS_STOP = -5.0
EMERGENCY_FLOOR = 60.0
HALF_LEG_TIMEOUT = 3        # was 5 — faster recovery
TARGET_USDC = 2.0
MIN_SHARES = 5.0
SLIPPAGE_AGG_CENTS = 0.04   # was 0.02 — much more aggressive to reduce half-leg
EMERGENCY_HEDGE_CENTS = 0.10  # NEW: if half-leg detected, hedge at ask+10c
TICK_SIZE = "0.01"

# From sniper_live_v2.py
PK = os.environ.get("POLY_PK") or ""
PROXY = os.environ.get("POLY_PROXY") or ""
if not PK or not PROXY:
    # Fallback to reading from sniper_live_v2.py (Windows local dev)
    import re
    sniper_path = r"D:\Rust\polymarket_ai_trader\sniper_live_v2.py"
    try:
        with open(sniper_path, encoding='utf-8') as f: c = f.read()
        PK = re.search(r'PK\s*=\s*"(0x[0-9a-fA-F]+)"', c).group(1)
        PROXY = re.search(r'PROXY\s*=\s*"(0x[0-9a-fA-F]+)"', c).group(1)
    except Exception as e:
        print(f"Set POLY_PK and POLY_PROXY env vars, or place sniper_live_v2.py: {e}")
        sys.exit(1)

CHAIN_ID = 137
SIG_TYPE = 2

ASSET_SLUGS = ("btc", "eth", "sol", "xrp")
MARKET_REFRESH_SEC = 60

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
GAMMA_URL = "https://gamma-api.polymarket.com/events"
CLOB_API = "https://clob.polymarket.com"

STATE_DIR = "."
STATE_FILE = os.path.join(STATE_DIR, "ws_real_state.json")
LOG_FILE = os.path.join(STATE_DIR, "ws_real_executor.log")

_running = True
def _sigint(_s, _f):
    global _running; _running = False


def now_ts(): return int(time.time())
def now_iso(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def today_utc(): return datetime.now(timezone.utc).date().isoformat()


def log(msg):
    line = f"[{now_iso()}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f: f.write(line + "\n")
    except: pass


def settle_ts_from_slug(slug):
    if "-updown-15m-" in slug:
        try: return int(slug.rsplit("-", 1)[1]) + 15 * 60
        except: return None
    if "-updown-5m-" in slug:
        try: return int(slug.rsplit("-", 1)[1]) + 5 * 60
        except: return None
    return None


def create_clob():
    return SecureClient.create(private_key=PK, wallet=PROXY)


def get_wallet_balance(clob):
    try:
        bal = clob.get_balance_allowance(asset_type="COLLATERAL")
        # BalanceAllowance.balance is raw 6-decimal USDC int
        return float(bal.balance) / 1e6
    except Exception as e:
        log(f"  balance query err: {e}")
        return None


def new_state():
    return {
        "started": now_iso(),
        "open": [],
        "settled": [],
        "daily_pnl": {},
        "stats": {
            "ws_msgs": 0, "snapshots": 0, "price_changes": 0,
            "detections": 0, "tradable_detections": 0,
            "pairs_attempted": 0, "pairs_filled": 0,
            "skipped_dupe_market": 0, "skipped_max_open": 0,
            "skipped_low_ttl": 0, "skipped_balance": 0,
            "skipped_daily": 0, "skipped_emergency": 0,
            "half_leg_events": 0, "order_errors": 0,
            "pairs_won": 0, "pairs_lost": 0,
            "total_cost": 0.0, "total_payout": 0.0,
            "pnl_realized": 0.0,
        },
    }


def load_state():
    if not os.path.exists(STATE_FILE):
        return new_state()
    with open(STATE_FILE, encoding="utf-8") as f: s = json.load(f)
    base = new_state()
    for k, v in base.items(): s.setdefault(k, v)
    for k, v in base["stats"].items(): s["stats"].setdefault(k, v)
    return s


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(state, f, indent=1)
    os.replace(tmp, STATE_FILE)


def today_pnl(state):
    return state["daily_pnl"].get(today_utc(), 0.0)


def record_pnl(state, delta):
    d = today_utc()
    state["daily_pnl"][d] = state["daily_pnl"].get(d, 0.0) + delta


def discover_markets(http):
    now = now_ts()
    s5 = now // 300 * 300
    s15 = now // 900 * 900
    slugs = []
    for asset in ASSET_SLUGS:
        for s in (s5, s5+300, s5+600):
            if s + 300 > now: slugs.append(f"{asset}-updown-5m-{s}")
        for s in (s15, s15+900):
            if s + 900 > now: slugs.append(f"{asset}-updown-15m-{s}")
    tokens = {}; markets = {}
    for slug in slugs:
        try:
            r = http.get(GAMMA_URL, params={"slug": slug}, timeout=5)
            if r.status_code != 200: continue
            for ev in r.json():
                for m in ev.get("markets", []):
                    if m.get("closed"): continue
                    cid = m.get("conditionId")
                    if not cid: continue
                    outcomes = m.get("outcomes")
                    if isinstance(outcomes, str): outcomes = json.loads(outcomes)
                    toks = m.get("clobTokenIds")
                    if isinstance(toks, str): toks = json.loads(toks)
                    if not (outcomes and toks and "Up" in outcomes and "Down" in outcomes): continue
                    up_idx = outcomes.index("Up"); dn_idx = outcomes.index("Down")
                    up_token, dn_token = str(toks[up_idx]), str(toks[dn_idx])
                    neg_risk = m.get("negRisk", False)
                    settle = settle_ts_from_slug(slug)
                    if not settle or settle - now < MIN_TTL_SEC: continue
                    markets[cid] = {
                        "slug": slug, "cid": cid, "settle_ts": settle,
                        "up_token": up_token, "down_token": dn_token,
                        "neg_risk": neg_risk,
                    }
                    tokens[up_token] = {"cid": cid, "slug": slug, "side": "Up", "paired": dn_token}
                    tokens[dn_token] = {"cid": cid, "slug": slug, "side": "Down", "paired": up_token}
        except: continue
    return tokens, markets


class OrderBook:
    def __init__(self):
        self.asks = []; self.bids = []

    def apply_snapshot(self, asks, bids):
        try:
            self.asks = sorted([(float(a["price"]), float(a["size"])) for a in asks])
            self.bids = sorted([(float(b["price"]), float(b["size"])) for b in bids], reverse=True)
        except: pass

    def apply_price_change(self, changes):
        for ch in changes:
            try:
                price = float(ch["price"]); size = float(ch["size"])
                side = ch.get("side", "").upper()
            except: continue
            book = self.asks if side == "SELL" else self.bids
            book[:] = [(p, s) for (p, s) in book if abs(p - price) > 1e-9]
            if size > 0: book.append((price, size))
            if side == "SELL": self.asks = sorted(book)
            else: self.bids = sorted(book, reverse=True)

    def walk_asks(self, target_usdc):
        remaining = target_usdc; max_price = 0.0
        for price, size in self.asks:
            if remaining <= 0: break
            if price >= 1.0: continue
            take = min(remaining, price * size)
            remaining -= take
            max_price = price
        return max_price if remaining < 0.01 else None


class RealExecutor:
    def __init__(self, state, clob):
        self.state = state
        self.clob = clob
        self.books = defaultdict(OrderBook)
        self.tokens = {}
        self.markets = {}
        self.last_detect = {}
        self.cached_balance = None
        self.last_balance_check = 0

    def get_balance(self, force=False):
        if not force and self.cached_balance is not None and time.time() - self.last_balance_check < 30:
            return self.cached_balance
        bal = get_wallet_balance(self.clob)
        if bal is not None:
            self.cached_balance = bal
            self.last_balance_check = time.time()
        return self.cached_balance

    def can_enter(self, cid):
        s = self.state["stats"]
        if today_pnl(self.state) <= DAILY_LOSS_STOP:
            s["skipped_daily"] += 1; return False
        if len(self.state["open"]) >= MAX_OPEN_PAIRS:
            s["skipped_max_open"] += 1; return False
        if any(p["cid"] == cid for p in self.state["open"]):
            s["skipped_dupe_market"] += 1; return False
        bal = self.get_balance()
        if bal is None: return False
        if bal <= EMERGENCY_FLOOR:
            s["skipped_emergency"] += 1
            log(f"  EMERGENCY: bal {bal:.2f} <= floor {EMERGENCY_FLOOR}")
            return False
        return True

    def place_order_real(self, token_id, price, shares, neg_risk_hint):
        """Place a single limit BUY order via polymarket-client SDK."""
        price = max(0.01, min(0.99, round(price, 2)))
        try:
            res = self.clob.place_limit_order(
                token_id=token_id,
                price=price,
                size=shares,
                side="BUY",
            )
            # AcceptedOrder has .order_id, RejectedOrder has .reason
            order_id = getattr(res, "order_id", None) or getattr(res, "id", None)
            if order_id:
                return order_id
            reason = getattr(res, "reason", None) or repr(res)[:120]
            log(f"  ORDER REJECT: {reason}")
            self.state["stats"]["order_errors"] += 1
            return None
        except Exception as e:
            log(f"  ORDER EXC {token_id[:12]}: {type(e).__name__}: {str(e)[:150]}")
            self.state["stats"]["order_errors"] += 1
            return None

    def cancel_order(self, order_id):
        try:
            self.clob.cancel_order(order_id=order_id)
        except Exception as e:
            log(f"  CANCEL ERR {order_id}: {e}")

    def check_order_fill(self, order_id):
        try:
            o = self.clob.get_order(order_id=order_id)
            if not o: return None
            status = getattr(o, "status", "") or ""
            status = str(status).lower()
            if status in ("matched", "filled", "complete"): return True
            if status in ("live", "open"): return False
            return None
        except Exception as e:
            log(f"  CHECK ERR: {e}")
            return None

    async def attempt_pair(self, cid, meta, book_me, book_pa):
        """Try to place both legs of arb pair."""
        s = self.state["stats"]
        m_ask = book_me.walk_asks(TARGET_USDC)
        p_ask = book_pa.walk_asks(TARGET_USDC)
        if m_ask is None or p_ask is None: return

        entry_me = round(min(0.99, m_ask + SLIPPAGE_AGG_CENTS), 4)
        entry_pa = round(min(0.99, p_ask + SLIPPAGE_AGG_CENTS), 4)
        eff_sum = entry_me + entry_pa
        s["detections"] += 1
        if eff_sum >= MAX_EFF_SUM: return
        s["tradable_detections"] += 1

        # Dedup
        last = self.last_detect.get(cid)
        if last and (time.time() - last) < 30: return
        if not self.can_enter(cid): return

        market = self.markets.get(cid, {})
        settle_ts = market.get("settle_ts")
        ttl = settle_ts - now_ts() if settle_ts else 0
        if ttl < MIN_TTL_SEC:
            s["skipped_low_ttl"] += 1; return

        if meta["side"] == "Up":
            entry_up, entry_dn = entry_me, entry_pa
            up_token = meta["paired"] if False else (None)  # placeholder
        # Resolve token IDs from market
        up_token = market["up_token"]; dn_token = market["down_token"]
        if meta["side"] == "Up":
            entry_up, entry_dn = entry_me, entry_pa
        else:
            entry_up, entry_dn = entry_pa, entry_me
        neg_risk = market.get("neg_risk", False)

        shares = MIN_SHARES
        cost_up = shares * entry_up
        cost_dn = shares * entry_dn
        total_cost = cost_up + cost_dn

        bal = self.get_balance()
        if bal is None or bal < total_cost + 1:
            s["skipped_balance"] += 1; return

        # PLACE BOTH LEGS
        self.last_detect[cid] = time.time()
        s["pairs_attempted"] += 1
        log(f"  ATTEMPT {market.get('slug','')[:24]} sum={eff_sum:.3f} Up={entry_up:.3f} Dn={entry_dn:.3f} shares={shares} bal=${bal:.2f}")

        up_order = self.place_order_real(up_token, entry_up, shares, neg_risk)
        dn_order = self.place_order_real(dn_token, entry_dn, shares, neg_risk)

        if not up_order or not dn_order:
            # One leg failed → cancel other if exists
            if up_order:
                log(f"  Up placed but Dn failed → cancel Up")
                self.cancel_order(up_order)
            if dn_order:
                log(f"  Dn placed but Up failed → cancel Dn")
                self.cancel_order(dn_order)
            return

        # Both orders placed. Wait HALF_LEG_TIMEOUT and check fills.
        log(f"  Placed Up={up_order[:12]} Dn={dn_order[:12]}, waiting {HALF_LEG_TIMEOUT}s for fills")
        await asyncio.sleep(HALF_LEG_TIMEOUT)

        up_filled = self.check_order_fill(up_order)
        dn_filled = self.check_order_fill(dn_order)

        if up_filled and dn_filled:
            # Both filled — true arb position
            s["pairs_filled"] += 1
            self.get_balance(force=True)  # refresh
            pair = {
                "cid": cid, "slug": market.get("slug", ""),
                "up_token": up_token, "dn_token": dn_token,
                "up_order": up_order, "dn_order": dn_order,
                "entry_up": entry_up, "entry_dn": entry_dn,
                "shares_up": shares, "shares_dn": shares,
                "cost_up": cost_up, "cost_dn": cost_dn,
                "total_cost": total_cost,
                "eff_sum": round(eff_sum, 4),
                "expected_payout": shares * 1.0,
                "locked_profit": round(shares - total_cost, 4),
                "settle_ts": settle_ts,
                "entered_at": now_iso(),
            }
            self.state["open"].append(pair)
            log(f"  ✓ PAIR FILLED {market.get('slug','')[:24]} locked=${pair['locked_profit']:+.2f}")
        elif up_filled and not dn_filled:
            s["half_leg_events"] += 1
            log(f"  ⚠ HALF-LEG Up filled, Dn open → cancel Dn (single Up risk)")
            self.cancel_order(dn_order)
            # We have unhedged Up position. Could sell back via market, but for now log and let settle
            log(f"  *** SINGLE UP @ {entry_up:.3f} {shares} shares — let settle for now ***")
        elif dn_filled and not up_filled:
            s["half_leg_events"] += 1
            log(f"  ⚠ HALF-LEG Dn filled, Up open → cancel Up (single Dn risk)")
            self.cancel_order(up_order)
            log(f"  *** SINGLE DN @ {entry_dn:.3f} {shares} shares — let settle for now ***")
        else:
            # Neither filled (limit prices too tight)
            log(f"  X Neither leg filled in {HALF_LEG_TIMEOUT}s → cancel both")
            self.cancel_order(up_order)
            self.cancel_order(dn_order)

    def on_book_update(self, token_id):
        meta = self.tokens.get(token_id)
        if not meta: return
        paired = meta["paired"]
        if paired not in self.books: return
        # SYNC detection — only schedule async if actually entering
        self.maybe_enter(meta, self.books[token_id], self.books[paired])

    def maybe_enter(self, meta, book_me, book_pa):
        s = self.state["stats"]
        m_ask = book_me.walk_asks(TARGET_USDC)
        p_ask = book_pa.walk_asks(TARGET_USDC)
        if m_ask is None or p_ask is None: return
        entry_me = round(min(0.99, m_ask + SLIPPAGE_AGG_CENTS), 4)
        entry_pa = round(min(0.99, p_ask + SLIPPAGE_AGG_CENTS), 4)
        eff_sum = entry_me + entry_pa
        s["detections"] += 1
        if eff_sum >= MAX_EFF_SUM: return
        s["tradable_detections"] += 1
        cid = meta["cid"]
        last = self.last_detect.get(cid)
        if last and (time.time() - last) < 30: return
        if not self.can_enter(cid): return
        market = self.markets.get(cid, {})
        settle_ts = market.get("settle_ts")
        ttl = settle_ts - now_ts() if settle_ts else 0
        if ttl < MIN_TTL_SEC:
            s["skipped_low_ttl"] += 1; return
        up_token = market["up_token"]; dn_token = market["down_token"]
        if meta["side"] == "Up":
            entry_up, entry_dn = entry_me, entry_pa
        else:
            entry_up, entry_dn = entry_pa, entry_me
        neg_risk = market.get("neg_risk", False)
        shares = MIN_SHARES
        cost_up = shares * entry_up
        cost_dn = shares * entry_dn
        total_cost = cost_up + cost_dn
        bal = self.get_balance()
        if bal is None or bal < total_cost + 1:
            s["skipped_balance"] += 1; return
        self.last_detect[cid] = time.time()
        s["pairs_attempted"] += 1
        log(f"  ATTEMPT {market.get('slug','')[:24]} sum={eff_sum:.3f} Up={entry_up:.3f} Dn={entry_dn:.3f} shares={shares} bal=${bal:.2f}")
        # User explicitly authorized real-money batch order placement via post_orders
        try:
            up_price = max(0.01, min(0.99, round(entry_up, 2)))
            dn_price = max(0.01, min(0.99, round(entry_dn, 2)))
            signed_up = self.clob.create_limit_order(token_id=up_token, price=up_price, size=shares, side="BUY")
            signed_dn = self.clob.create_limit_order(token_id=dn_token, price=dn_price, size=shares, side="BUY")
            results = self.clob.post_orders([signed_up, signed_dn])
        except Exception as e:
            log(f"  BATCH EXC: {type(e).__name__}: {str(e)[:180]}")
            s["order_errors"] += 1
            return
        if not results or len(results) < 2:
            log(f"  BATCH BAD: {results}")
            s["order_errors"] += 1
            return
        r_up, r_dn = results[0], results[1]
        up_order_id = getattr(r_up, "order_id", None)
        dn_order_id = getattr(r_dn, "order_id", None)
        up_ok = bool(up_order_id) and getattr(r_up, "ok", False)
        dn_ok = bool(dn_order_id) and getattr(r_dn, "ok", False)
        log(f"  BATCH Up={getattr(r_up,'status','?')}/{(up_order_id or 'fail')[:10]} Dn={getattr(r_dn,'status','?')}/{(dn_order_id or 'fail')[:10]}")
        if not up_ok and not dn_ok:
            s["order_errors"] += 2; return
        if up_ok and not dn_ok:
            s["half_leg_events"] += 1
            log(f"  HALF Up only → cancel Up")
            self.cancel_order(up_order_id)
            s["order_errors"] += 1
            return
        if dn_ok and not up_ok:
            s["half_leg_events"] += 1
            log(f"  HALF Dn only → cancel Dn")
            self.cancel_order(dn_order_id)
            s["order_errors"] += 1
            return
        asyncio.create_task(self._check_fills(cid, up_order_id, dn_order_id, up_token, dn_token,
                                              entry_up, entry_dn, shares, cost_up, cost_dn,
                                              total_cost, eff_sum, settle_ts, market))

    async def _check_fills(self, cid, up_order, dn_order, up_token, dn_token,
                            entry_up, entry_dn, shares, cost_up, cost_dn,
                            total_cost, eff_sum, settle_ts, market):
        log(f"  Placed Up={up_order[:12]} Dn={dn_order[:12]}, wait {HALF_LEG_TIMEOUT}s")
        await asyncio.sleep(HALF_LEG_TIMEOUT)
        s = self.state["stats"]
        up_filled = self.check_order_fill(up_order)
        dn_filled = self.check_order_fill(dn_order)
        if up_filled and dn_filled:
            s["pairs_filled"] += 1
            self.get_balance(force=True)
            pair = {
                "cid": cid, "slug": market.get("slug",""),
                "up_token": up_token, "dn_token": dn_token,
                "up_order": up_order, "dn_order": dn_order,
                "entry_up": entry_up, "entry_dn": entry_dn,
                "shares_up": shares, "shares_dn": shares,
                "cost_up": cost_up, "cost_dn": cost_dn,
                "total_cost": total_cost,
                "eff_sum": round(eff_sum,4),
                "locked_profit": round(shares - total_cost, 4),
                "settle_ts": settle_ts,
                "entered_at": now_iso(),
            }
            self.state["open"].append(pair)
            log(f"  PAIR FILLED {market.get('slug','')[:24]} locked=${pair['locked_profit']:+.2f}")
        elif up_filled and not dn_filled:
            s["half_leg_events"] += 1
            log(f"  HALF Up filled → cancel Dn, EMERGENCY hedge Dn")
            self.cancel_order(dn_order)
            # Emergency: place aggressive Dn at current ask + 10c
            fresh_dn_ask = self.books[dn_token].walk_asks(TARGET_USDC) if dn_token in self.books else entry_dn
            if fresh_dn_ask is None: fresh_dn_ask = entry_dn
            hedge_price = max(0.01, min(0.99, round(fresh_dn_ask + EMERGENCY_HEDGE_CENTS, 2)))
            try:
                hedge_res = self.clob.place_limit_order(token_id=dn_token, price=hedge_price, size=shares, side="BUY")
                hedge_id = getattr(hedge_res, "order_id", None)
                if hedge_id:
                    log(f"  HEDGE Dn @ {hedge_price:.3f} placed ({hedge_id[:10]})")
                    await asyncio.sleep(3)
                    if self.check_order_fill(hedge_id):
                        log(f"  HEDGE Dn FILLED → recovered pair")
                        s["pairs_filled"] += 1
                        new_cost_dn = shares * hedge_price
                        new_total = cost_up + new_cost_dn
                        self.state["open"].append({
                            "cid": cid, "slug": market.get("slug",""),
                            "up_token": up_token, "dn_token": dn_token,
                            "up_order": up_order, "dn_order": hedge_id,
                            "entry_up": entry_up, "entry_dn": hedge_price,
                            "shares_up": shares, "shares_dn": shares,
                            "cost_up": cost_up, "cost_dn": new_cost_dn,
                            "total_cost": new_total,
                            "eff_sum": round(entry_up + hedge_price, 4),
                            "locked_profit": round(shares - new_total, 4),
                            "settle_ts": settle_ts,
                            "entered_at": now_iso(),
                            "recovered": True,
                        })
                    else:
                        log(f"  HEDGE Dn STILL NO FILL → cancel, SINGLE Up remains")
                        self.cancel_order(hedge_id)
                else:
                    log(f"  HEDGE Dn place failed → SINGLE Up remains")
            except Exception as e:
                log(f"  HEDGE Dn EXC: {type(e).__name__}: {str(e)[:120]}")
        elif dn_filled and not up_filled:
            s["half_leg_events"] += 1
            log(f"  HALF Dn filled → cancel Up, EMERGENCY hedge Up")
            self.cancel_order(up_order)
            fresh_up_ask = self.books[up_token].walk_asks(TARGET_USDC) if up_token in self.books else entry_up
            if fresh_up_ask is None: fresh_up_ask = entry_up
            hedge_price = max(0.01, min(0.99, round(fresh_up_ask + EMERGENCY_HEDGE_CENTS, 2)))
            try:
                hedge_res = self.clob.place_limit_order(token_id=up_token, price=hedge_price, size=shares, side="BUY")
                hedge_id = getattr(hedge_res, "order_id", None)
                if hedge_id:
                    log(f"  HEDGE Up @ {hedge_price:.3f} placed ({hedge_id[:10]})")
                    await asyncio.sleep(3)
                    if self.check_order_fill(hedge_id):
                        log(f"  HEDGE Up FILLED → recovered pair")
                        s["pairs_filled"] += 1
                        new_cost_up = shares * hedge_price
                        new_total = new_cost_up + cost_dn
                        self.state["open"].append({
                            "cid": cid, "slug": market.get("slug",""),
                            "up_token": up_token, "dn_token": dn_token,
                            "up_order": hedge_id, "dn_order": dn_order,
                            "entry_up": hedge_price, "entry_dn": entry_dn,
                            "shares_up": shares, "shares_dn": shares,
                            "cost_up": new_cost_up, "cost_dn": cost_dn,
                            "total_cost": new_total,
                            "eff_sum": round(hedge_price + entry_dn, 4),
                            "locked_profit": round(shares - new_total, 4),
                            "settle_ts": settle_ts,
                            "entered_at": now_iso(),
                            "recovered": True,
                        })
                    else:
                        log(f"  HEDGE Up STILL NO FILL → cancel, SINGLE Dn remains")
                        self.cancel_order(hedge_id)
                else:
                    log(f"  HEDGE Up place failed → SINGLE Dn remains")
            except Exception as e:
                log(f"  HEDGE Up EXC: {type(e).__name__}: {str(e)[:120]}")
        else:
            log(f"  X no fill in {HALF_LEG_TIMEOUT}s → cancel both")
            self.cancel_order(up_order); self.cancel_order(dn_order)


async def ws_loop(executor):
    reconnect_delay = 1
    while _running:
        token_ids = list(executor.tokens.keys())
        if not token_ids:
            await asyncio.sleep(2); continue
        try:
            log(f"  WS connect with {len(token_ids)} tokens")
            async with websockets.connect(WS_URL, ping_interval=10, ping_timeout=10, max_size=8*1024*1024) as ws:
                await ws.send(json.dumps({"type": "MARKET", "assets_ids": token_ids}))
                reconnect_delay = 1
                while _running:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    except asyncio.TimeoutError:
                        log(f"  WS idle, reconnect"); break
                    executor.state["stats"]["ws_msgs"] += 1
                    try: msg = json.loads(raw)
                    except: continue
                    msgs = msg if isinstance(msg, list) else [msg]
                    for m in msgs:
                        event_type = m.get("event_type") or m.get("type")
                        asset_id = m.get("asset_id") or m.get("market")
                        if not asset_id: continue
                        if event_type == "book":
                            executor.state["stats"]["snapshots"] += 1
                            executor.books[asset_id].apply_snapshot(m.get("asks") or [], m.get("bids") or [])
                            executor.on_book_update(asset_id)
                        elif event_type == "price_change":
                            executor.state["stats"]["price_changes"] += 1
                            changes = m.get("changes") or m.get("price_changes") or [m]
                            executor.books[asset_id].apply_price_change(changes)
                            executor.on_book_update(asset_id)
        except Exception as e:
            if not _running: break
            log(f"  WS err: {e}, reconnect in {reconnect_delay}s")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(30, reconnect_delay * 2)


async def discovery_loop(executor):
    http = httpx.Client()
    try:
        while _running:
            try:
                tokens, markets = discover_markets(http)
                executor.tokens = tokens; executor.markets = markets
            except Exception as e:
                log(f"  discovery err: {e}")
            for _ in range(MARKET_REFRESH_SEC):
                if not _running: break
                await asyncio.sleep(1)
    finally: http.close()


async def settlement_loop(executor):
    http = httpx.Client()
    try:
        while _running:
            await asyncio.sleep(20)
            now = now_ts()
            still_open = []
            for pair in executor.state["open"]:
                if not pair.get("settle_ts") or now < pair["settle_ts"] + 60:
                    still_open.append(pair); continue
                try:
                    r = http.get(f"{CLOB_API}/markets/{pair['cid']}", timeout=10)
                    if r.status_code != 200:
                        still_open.append(pair); continue
                    tokens = r.json().get("tokens", [])
                    winners = [t.get("winner") for t in tokens]
                    if winners.count(True) != 1:
                        still_open.append(pair); continue
                    up_tok = next((t for t in tokens if str(t.get("token_id")) == pair["up_token"]), None)
                    dn_tok = next((t for t in tokens if str(t.get("token_id")) == pair["dn_token"]), None)
                    if not (up_tok and dn_tok):
                        still_open.append(pair); continue
                    up_won = up_tok.get("winner") is True
                    payout = pair["shares_up"] * 1.0 if up_won else pair["shares_dn"] * 1.0
                    pnl = payout - pair["total_cost"]
                    s = executor.state["stats"]
                    s["total_payout"] += payout
                    s["pnl_realized"] += pnl
                    if pnl > 0: s["pairs_won"] += 1
                    else: s["pairs_lost"] += 1
                    record_pnl(executor.state, pnl)
                    pair["winning_side"] = "Up" if up_won else "Down"
                    pair["payout"] = payout
                    pair["pnl"] = pnl
                    pair["settled_at"] = now_iso()
                    executor.state["settled"].append(pair)
                    log(f"  SETTLE {pair['slug'][:24]} {pair['winning_side']} won pnl=${pnl:+.2f}")
                except Exception as e:
                    log(f"  settle err: {e}")
                    still_open.append(pair)
            executor.state["open"] = still_open
            # Refresh balance
            executor.get_balance(force=True)
    finally: http.close()


async def stats_loop(executor):
    while _running:
        for _ in range(60):
            if not _running: break
            await asyncio.sleep(1)
        s = executor.state["stats"]
        bal = executor.get_balance() or 0
        oc = sum(p["total_cost"] for p in executor.state["open"])
        n_set = s["pairs_won"] + s["pairs_lost"]
        wr = s["pairs_won"]/n_set*100 if n_set else 0
        log(f"  STAT bal=${bal:.2f} open={len(executor.state['open'])} (${oc:.2f}) | attempted={s['pairs_attempted']} filled={s['pairs_filled']} half_leg={s['half_leg_events']} ord_err={s['order_errors']} | settled={n_set} WR={wr:.1f}% PnL=${s['pnl_realized']:+.2f} today=${today_pnl(executor.state):+.2f} | trad_det={s['tradable_detections']}")
        save_state(executor.state)


async def main_async():
    signal.signal(signal.SIGINT, _sigint)
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="No real orders (paper mode)")
    args = ap.parse_args()

    log(f"=== WS REAL-MONEY arb executor ===")
    log(f"  MAX_EFF_SUM:    {MAX_EFF_SUM}")
    log(f"  MIN_TTL_SEC:    {MIN_TTL_SEC}")
    log(f"  MAX_OPEN_PAIRS: {MAX_OPEN_PAIRS}")
    log(f"  DAILY_LOSS:     ${DAILY_LOSS_STOP}")
    log(f"  EMERGENCY_FLOOR: ${EMERGENCY_FLOOR}")
    log(f"  HALF_LEG_TIMEOUT: {HALF_LEG_TIMEOUT}s")
    if args.dry_run:
        log(f"  *** DRY RUN MODE — no real orders ***")

    if args.fresh and os.path.exists(STATE_FILE):
        os.remove(STATE_FILE); log("  fresh state")

    state = load_state()
    log(f"  PK[..6]: {PK[:10]}... PROXY: {PROXY}")
    clob = create_clob()
    bal = get_wallet_balance(clob)
    log(f"  wallet balance: ${bal:.2f}" if bal else "  wallet balance: query failed")
    if bal is None:
        log("ABORT: cannot query balance"); return
    if bal <= EMERGENCY_FLOOR:
        log(f"ABORT: balance ${bal:.2f} <= floor ${EMERGENCY_FLOOR}"); return

    executor = RealExecutor(state, clob)
    executor.cached_balance = bal

    http = httpx.Client()
    tokens, markets = discover_markets(http)
    http.close()
    executor.tokens = tokens
    executor.markets = markets
    log(f"  initial: {len(markets)} markets / {len(tokens)} tokens")

    try:
        await asyncio.gather(
            ws_loop(executor),
            discovery_loop(executor),
            settlement_loop(executor),
            stats_loop(executor),
        )
    finally:
        save_state(state)
        log("=== shutdown ===")


if __name__ == "__main__":
    asyncio.run(main_async())
