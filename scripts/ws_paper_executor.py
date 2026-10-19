"""WS-based paper executor — Phase 2.

Watches arb detections in real-time, simulates entering both legs immediately.
NO real money. Tracks hypothetical PnL with full position tracking + settlement.

Configuration:
  INITIAL_BALANCE = $76
  MAX_OPEN_PAIRS  = 12 (capital constraint)
  MIN_TTL_SEC     = 60 (skip too-late entries)
  MAX_EFF_SUM     = 0.95 (only true arb)
  TARGET_USDC     = $2 per leg
  MIN_SHARES      = 5 (Polymarket minimum)

Output:
  D:\\polymarket_state\\ws_paper_executor.log
  D:\\polymarket_state\\ws_paper_state.json
"""
import argparse, asyncio, json, os, signal, sys, time, traceback
from collections import defaultdict
from datetime import datetime, timezone

import httpx
try:
    import websockets
except ImportError:
    print("pip install websockets"); sys.exit(1)

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except: pass

# === Config ===
INITIAL_BALANCE = 76.0
MAX_OPEN_PAIRS = 12       # leg count = 2x, so 24 legs max
MIN_TTL_SEC = 60          # need >=60s window to safely enter
MAX_EFF_SUM = 0.95
TARGET_USDC = 2.0
MIN_SHARES = 5.0
DAILY_LOSS_STOP = -30.0
EMERGENCY_FLOOR = 30.0
SLIPPAGE_AGG_CENTS = 0.01

ASSET_SLUGS = ("btc", "eth", "sol", "xrp")
MARKET_REFRESH_SEC = 60

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
GAMMA_URL = "https://gamma-api.polymarket.com/events"
CLOB_API = "https://clob.polymarket.com"

STATE_DIR = r"."
STATE_FILE = os.path.join(STATE_DIR, "ws_paper_state.json")
LOG_FILE = os.path.join(STATE_DIR, "ws_paper_executor.log")

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


def new_state():
    return {
        "sim_balance": INITIAL_BALANCE,
        "started": now_iso(),
        "started_balance": INITIAL_BALANCE,
        "open": [],
        "settled": [],
        "daily_pnl": {},
        "stats": {
            "ws_msgs": 0, "snapshots": 0, "price_changes": 0,
            "detections": 0, "tradable_detections": 0,
            "pairs_entered": 0, "legs_entered": 0,
            "skipped_dupe_market": 0, "skipped_max_open": 0,
            "skipped_low_ttl": 0, "skipped_balance": 0,
            "skipped_daily": 0, "skipped_emergency": 0,
            "pairs_won": 0, "pairs_lost": 0, "pairs_partial": 0,
            "total_cost": 0.0, "total_payout": 0.0,
            "pnl_realized": 0.0,
            "settle_errors": 0,
        },
    }


def load_state():
    if not os.path.exists(STATE_FILE):
        log(f"NEW state ${INITIAL_BALANCE:.2f}")
        return new_state()
    with open(STATE_FILE, encoding="utf-8") as f:
        state = json.load(f)
    base = new_state()
    for k, v in base.items(): state.setdefault(k, v)
    for k, v in base["stats"].items(): state["stats"].setdefault(k, v)
    log(f"LOADED bal=${state['sim_balance']:.2f} open={len(state['open'])} settled={len(state['settled'])} pnl=${state['stats']['pnl_realized']:+.2f}")
    return state


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
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
    tokens = {}
    markets = {}
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
                    settle = settle_ts_from_slug(slug)
                    if not settle or settle - now < MIN_TTL_SEC: continue
                    markets[cid] = {
                        "slug": slug, "cid": cid, "settle_ts": settle,
                        "up_token": up_token, "down_token": dn_token,
                    }
                    tokens[up_token] = {"cid": cid, "slug": slug, "side": "Up", "paired": dn_token}
                    tokens[dn_token] = {"cid": cid, "slug": slug, "side": "Down", "paired": up_token}
        except Exception:
            continue
    return tokens, markets


class OrderBook:
    def __init__(self):
        self.asks = []
        self.bids = []

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


class Executor:
    def __init__(self, state):
        self.state = state
        self.books = defaultdict(OrderBook)
        self.tokens = {}
        self.markets = {}
        self.last_detect = {}  # cid -> ts (dedup)

    def can_enter(self, cid):
        s = self.state["stats"]
        if today_pnl(self.state) <= DAILY_LOSS_STOP:
            s["skipped_daily"] += 1; return False
        if len(self.state["open"]) >= MAX_OPEN_PAIRS:
            s["skipped_max_open"] += 1; return False
        # already have pair in this cid?
        if any(p["cid"] == cid for p in self.state["open"]):
            s["skipped_dupe_market"] += 1; return False
        # emergency floor
        open_cost = sum(p["cost_up"] + p["cost_dn"] for p in self.state["open"])
        if self.state["sim_balance"] + open_cost <= EMERGENCY_FLOOR:
            s["skipped_emergency"] += 1; return False
        return True

    def on_book_update(self, token_id):
        meta = self.tokens.get(token_id)
        if not meta: return
        paired = meta["paired"]
        if paired not in self.books: return
        book_me = self.books[token_id]
        book_pa = self.books[paired]
        m_ask = book_me.walk_asks(TARGET_USDC)
        p_ask = book_pa.walk_asks(TARGET_USDC)
        if m_ask is None or p_ask is None: return

        # Effective entry per leg
        entry_me = round(min(0.99, m_ask + SLIPPAGE_AGG_CENTS), 4)
        entry_pa = round(min(0.99, p_ask + SLIPPAGE_AGG_CENTS), 4)
        eff_sum = entry_me + entry_pa
        self.state["stats"]["detections"] += 1
        if eff_sum >= MAX_EFF_SUM: return

        cid = meta["cid"]
        self.state["stats"]["tradable_detections"] += 1

        # Dedup: only act once per market within 30s
        last = self.last_detect.get(cid)
        if last and (time.time() - last) < 30:
            return

        # Check capacity
        if not self.can_enter(cid): return

        market = self.markets.get(cid, {})
        settle_ts = market.get("settle_ts")
        ttl = settle_ts - now_ts() if settle_ts else 0
        if ttl < MIN_TTL_SEC:
            self.state["stats"]["skipped_low_ttl"] += 1; return

        # Decide which side maps to Up/Down
        if meta["side"] == "Up":
            entry_up, entry_dn = entry_me, entry_pa
            up_token = token_id; dn_token = paired
        else:
            entry_up, entry_dn = entry_pa, entry_me
            up_token = paired; dn_token = token_id

        # Fixed MIN_SHARES per leg = true arb (equal shares) + capital efficient
        shares_up = shares_dn = MIN_SHARES
        cost_up = round(shares_up * entry_up, 4)
        cost_dn = round(shares_dn * entry_dn, 4)
        total_cost = cost_up + cost_dn

        if self.state["sim_balance"] < total_cost:
            self.state["stats"]["skipped_balance"] += 1; return

        # ENTER
        self.last_detect[cid] = time.time()
        self.state["sim_balance"] -= total_cost
        s = self.state["stats"]
        s["pairs_entered"] += 1
        s["legs_entered"] += 2
        s["total_cost"] += total_cost

        # Locked profit estimate (will get max(shares_up,shares_dn) × $1)
        expected_payout = max(shares_up, shares_dn) * 1.0
        locked_profit = expected_payout - total_cost

        pair = {
            "cid": cid, "slug": market.get("slug", ""),
            "up_token": up_token, "dn_token": dn_token,
            "entry_up": entry_up, "entry_dn": entry_dn,
            "shares_up": shares_up, "shares_dn": shares_dn,
            "cost_up": cost_up, "cost_dn": cost_dn,
            "total_cost": total_cost,
            "eff_sum": round(eff_sum, 4),
            "expected_payout": round(expected_payout, 4),
            "locked_profit": round(locked_profit, 4),
            "ttl_at_entry": ttl,
            "settle_ts": settle_ts,
            "entered_at": now_iso(),
            "entered_ts": now_ts(),
        }
        self.state["open"].append(pair)
        log(f"  PAIR {market.get('slug','')[:24]} Up={entry_up:.3f}/${cost_up:.2f} Dn={entry_dn:.3f}/${cost_dn:.2f} sum={eff_sum:.3f} locked=+${locked_profit:.2f} ttl={ttl}s bal=${self.state['sim_balance']:.2f}")


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
                        log(f"  WS idle 30s, reconnect")
                        break
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
                executor.tokens = tokens
                executor.markets = markets
            except Exception as e:
                log(f"  discovery err: {e}")
            for _ in range(MARKET_REFRESH_SEC):
                if not _running: break
                await asyncio.sleep(1)
    finally:
        http.close()


async def settlement_loop(executor):
    """Poll CLOB to resolve markets past settle_ts."""
    http = httpx.Client()
    try:
        while _running:
            await asyncio.sleep(15)
            now = now_ts()
            still_open = []
            for pair in executor.state["open"]:
                if not pair.get("settle_ts") or now < pair["settle_ts"] + 30:
                    still_open.append(pair); continue
                try:
                    r = http.get(f"{CLOB_API}/markets/{pair['cid']}", timeout=10)
                    if r.status_code != 200:
                        still_open.append(pair); continue
                    tokens = r.json().get("tokens", [])
                    winners = [t.get("winner") for t in tokens]
                    if winners.count(True) != 1:
                        still_open.append(pair); continue
                    # Find which side won
                    up_tok = next((t for t in tokens if str(t.get("token_id")) == pair["up_token"]), None)
                    dn_tok = next((t for t in tokens if str(t.get("token_id")) == pair["dn_token"]), None)
                    if not (up_tok and dn_tok):
                        still_open.append(pair); continue
                    up_won = up_tok.get("winner") is True
                    if up_won:
                        payout = pair["shares_up"] * 1.0
                        winning_side = "Up"
                    else:
                        payout = pair["shares_dn"] * 1.0
                        winning_side = "Down"
                    pnl = payout - pair["total_cost"]
                    executor.state["sim_balance"] += payout
                    s = executor.state["stats"]
                    s["total_payout"] += payout
                    s["pnl_realized"] += pnl
                    if pnl > 0: s["pairs_won"] += 1
                    else: s["pairs_lost"] += 1
                    record_pnl(executor.state, pnl)
                    pair["winning_side"] = winning_side
                    pair["payout"] = payout
                    pair["pnl"] = pnl
                    pair["settled_at"] = now_iso()
                    executor.state["settled"].append(pair)
                    log(f"  SETTLE {pair['slug'][:24]} {winning_side} won → payout=${payout:.2f} cost=${pair['total_cost']:.2f} pnl=${pnl:+.2f} bal=${executor.state['sim_balance']:.2f}")
                except Exception as e:
                    log(f"  settle err {pair['cid'][:10]}: {e}")
                    still_open.append(pair)
            executor.state["open"] = still_open
    finally:
        http.close()


async def stats_loop(executor):
    while _running:
        for _ in range(60):
            if not _running: break
            await asyncio.sleep(1)
        s = executor.state["stats"]
        oc = sum(p["total_cost"] for p in executor.state["open"])
        total = executor.state["sim_balance"] + oc
        delta = total - executor.state.get("started_balance", INITIAL_BALANCE)
        n_settled = s["pairs_won"] + s["pairs_lost"]
        wr = s["pairs_won"]/n_settled*100 if n_settled else 0
        roi = s["pnl_realized"]/max(s["total_cost"],1)*100 if n_settled else 0
        log(f"  STAT bal=${executor.state['sim_balance']:.2f} open={len(executor.state['open'])} (${oc:.2f}) total=${total:.2f} delta=${delta:+.2f} | pairs_entered={s['pairs_entered']} settled={n_settled} WR={wr:.1f}% pnl=${s['pnl_realized']:+.2f} ROI={roi:+.2f}% | trad_det={s['tradable_detections']} skip_dupe={s['skipped_dupe_market']} skip_max={s['skipped_max_open']}")
        save_state(executor.state)


async def main_async():
    signal.signal(signal.SIGINT, _sigint)
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()

    log(f"=== WS paper executor (auto-trade on arb detection) ===")
    log(f"  start_balance: ${INITIAL_BALANCE}")
    log(f"  max_open: {MAX_OPEN_PAIRS} pairs")
    log(f"  filters: sum<{MAX_EFF_SUM}, ttl>={MIN_TTL_SEC}s, no dupe market")

    if args.fresh and os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        log("  fresh state")

    state = load_state()
    executor = Executor(state)

    # Initial discovery
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
        save_state(executor.state)
        log("=== shutdown ===")


if __name__ == "__main__":
    asyncio.run(main_async())
