"""WS-based arb observer — Phase 1 (observation only, no orders).

Architecture:
  1. Discover active BTC/ETH/SOL/XRP 5m+15m markets via gamma API
  2. Subscribe to MARKET channel for all token IDs
  3. Maintain local orderbook (bids+asks per token) from snapshots + deltas
  4. On every update, recompute sum(walked_Up + walked_Down) per market
  5. Log detections when sum drops below thresholds
  6. Re-discover markets every 60s (as they settle)

Compare with HTTP scanner running in parallel:
  - HTTP scanner: ~1100ms cycle (PH) → catches arb only if persists 1s+
  - WS observer:   sub-100ms reaction → should catch fleeting arbs too

NO ORDERS. Pure observation.
"""
import asyncio, json, os, signal, sys, time
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

ASSET_SLUGS = ("btc", "eth", "sol", "xrp")
TARGET_USDC = 2.0
LOG_THRESHOLD = 1.05    # log all sum<1.05 (analysis)
TRADABLE_THRESHOLD = 0.95
MARKET_REFRESH_SEC = 60
MIN_TIME_LEFT_SEC = 30

STATE_DIR = r"."
DETECT_LOG = os.path.join(STATE_DIR, "ws_arb_detections.jsonl")
STATUS_LOG = os.path.join(STATE_DIR, "ws_observer.log")

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
GAMMA_URL = "https://gamma-api.polymarket.com/events"

_running = True
def _sigint(_s, _f):
    global _running; _running = False


def now_ts(): return int(time.time())
def now_iso(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg):
    line = f"[{now_iso()}] {msg}"
    print(line, flush=True)
    try:
        with open(STATUS_LOG, "a", encoding="utf-8") as f: f.write(line + "\n")
    except: pass


def settle_ts_from_slug(slug):
    if "-updown-15m-" in slug:
        try: return int(slug.rsplit("-", 1)[1]) + 15 * 60
        except: return None
    if "-updown-5m-" in slug:
        try: return int(slug.rsplit("-", 1)[1]) + 5 * 60
        except: return None
    return None


def discover_markets(http):
    """Return {token_id: market_info}, where market_info has cid, slug, side, paired_token."""
    now = now_ts()
    s5 = now // 300 * 300
    s15 = now // 900 * 900
    slugs = []
    for asset in ASSET_SLUGS:
        for s in (s5, s5+300, s5+600):
            if s + 300 > now: slugs.append(f"{asset}-updown-5m-{s}")
        for s in (s15, s15+900):
            if s + 900 > now: slugs.append(f"{asset}-updown-15m-{s}")

    tokens = {}  # token_id -> {cid, slug, side, paired}
    markets = {}  # cid -> {slug, settle_ts, up_token, down_token}

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
                    if not settle or settle - now < MIN_TIME_LEFT_SEC: continue
                    markets[cid] = {
                        "slug": slug, "cid": cid, "settle_ts": settle,
                        "up_token": up_token, "down_token": dn_token,
                    }
                    tokens[up_token] = {"cid": cid, "slug": slug, "side": "Up", "paired": dn_token}
                    tokens[dn_token] = {"cid": cid, "slug": slug, "side": "Down", "paired": up_token}
        except Exception as e:
            continue
    return tokens, markets


class OrderBook:
    """Maintain top-of-book + walk for one token."""
    def __init__(self):
        self.asks = []   # list of (price, size) sorted ascending
        self.bids = []   # list of (price, size) sorted descending
        self.last_update = 0

    def apply_snapshot(self, asks, bids):
        try:
            self.asks = sorted([(float(a["price"]), float(a["size"])) for a in asks])
            self.bids = sorted([(float(b["price"]), float(b["size"])) for b in bids], reverse=True)
        except: pass
        self.last_update = time.time()

    def apply_price_change(self, changes):
        """changes: list of {price, side, size}. size=0 removes level."""
        for ch in changes:
            try:
                price = float(ch["price"])
                size = float(ch["size"])
                side = ch.get("side", "").upper()
            except: continue
            book = self.asks if side == "SELL" else self.bids
            # Remove existing level at this price
            book[:] = [(p, s) for (p, s) in book if abs(p - price) > 1e-9]
            if size > 0:
                book.append((price, size))
            if side == "SELL":
                self.asks = sorted(book)
            else:
                self.bids = sorted(book, reverse=True)
        self.last_update = time.time()

    def walk_asks(self, target_usdc):
        """Returns max_price needed to fill target_usdc, or None."""
        remaining = target_usdc
        max_price = 0.0
        for price, size in self.asks:
            if remaining <= 0: break
            if price >= 1.0: continue
            take = min(remaining, price * size)
            remaining -= take
            max_price = price
        return max_price if remaining < 0.01 else None


class ArbState:
    def __init__(self):
        self.books = defaultdict(OrderBook)  # token_id -> OrderBook
        self.tokens = {}  # token_id -> market_info
        self.markets = {}  # cid -> market_info
        self.last_detect = {}  # cid -> {ts, eff_sum} to dedup
        self.stats = {
            "ws_msgs": 0, "snapshots": 0, "price_changes": 0,
            "tick_size_changes": 0, "other_msgs": 0,
            "detections": 0, "tradable_detections": 0,
            "discoveries": 0,
        }

    def detect(self, token_id):
        """On any book update, check arb for this market."""
        meta = self.tokens.get(token_id)
        if not meta: return
        paired = meta["paired"]
        if paired not in self.books: return
        book_me = self.books[token_id]
        book_pa = self.books[paired]
        m_ask = book_me.walk_asks(TARGET_USDC)
        p_ask = book_pa.walk_asks(TARGET_USDC)
        if m_ask is None or p_ask is None: return
        raw_sum = m_ask + p_ask
        eff_sum = (m_ask + 0.01) + (p_ask + 0.01)  # +1c slip per leg
        if eff_sum >= LOG_THRESHOLD: return

        cid = meta["cid"]
        # Dedup: same market, only re-log if eff_sum dropped 0.005+
        last = self.last_detect.get(cid)
        if last and (time.time() - last["ts"] < 1) and (eff_sum >= last["eff_sum"] - 0.005):
            return
        self.last_detect[cid] = {"ts": time.time(), "eff_sum": eff_sum}

        is_tradable = eff_sum < TRADABLE_THRESHOLD
        self.stats["detections"] += 1
        if is_tradable: self.stats["tradable_detections"] += 1

        if meta["side"] == "Up":
            up_ask = m_ask; dn_ask = p_ask
        else:
            up_ask = p_ask; dn_ask = m_ask
        market = self.markets.get(cid, {})
        det = {
            "ts": time.time(),
            "iso": now_iso(),
            "cid": cid, "slug": market.get("slug",""),
            "settle_ts": market.get("settle_ts"),
            "time_to_settle": market.get("settle_ts", 0) - now_ts() if market.get("settle_ts") else None,
            "raw_sum": round(raw_sum, 4),
            "eff_sum": round(eff_sum, 4),
            "up_ask": round(up_ask, 4),
            "down_ask": round(dn_ask, 4),
            "tradable": is_tradable,
            "trigger_token": token_id[:20],
        }
        with open(DETECT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(det) + "\n")
        if is_tradable:
            log(f"  ⭐ TRADABLE  {market.get('slug','')[:30]:<32} sum={eff_sum:.3f} up={up_ask:.3f} dn={dn_ask:.3f} ttl={det['time_to_settle']}s")
        else:
            # Quiet log: only every 30s near-arb
            if last is None or (time.time() - (last["ts"] if last else 0) > 30):
                log(f"  near  {market.get('slug','')[:30]:<32} sum={eff_sum:.3f}")


async def ws_loop(state):
    """Connect WS, subscribe to all tokens, process messages."""
    reconnect_delay = 1
    while _running:
        token_ids = list(state.tokens.keys())
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
                        log(f"  WS idle 30s, forcing reconnect")
                        break
                    state.stats["ws_msgs"] += 1
                    try:
                        msg = json.loads(raw)
                    except: continue
                    msgs = msg if isinstance(msg, list) else [msg]
                    for m in msgs:
                        event_type = m.get("event_type") or m.get("type")
                        asset_id = m.get("asset_id") or m.get("market")
                        if not asset_id: continue
                        if event_type == "book":
                            state.stats["snapshots"] += 1
                            asks = m.get("asks") or []
                            bids = m.get("bids") or []
                            state.books[asset_id].apply_snapshot(asks, bids)
                            state.detect(asset_id)
                        elif event_type == "price_change":
                            state.stats["price_changes"] += 1
                            changes = m.get("changes") or m.get("price_changes") or [m]
                            state.books[asset_id].apply_price_change(changes)
                            state.detect(asset_id)
                        elif event_type == "tick_size_change":
                            state.stats["tick_size_changes"] += 1
                        else:
                            state.stats["other_msgs"] += 1
        except Exception as e:
            if not _running: break
            log(f"  WS err: {e}, reconnect in {reconnect_delay}s")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(30, reconnect_delay * 2)


async def discovery_loop(state):
    """Periodically rediscover markets."""
    http = httpx.Client()
    try:
        while _running:
            try:
                tokens, markets = discover_markets(http)
                state.tokens = tokens
                state.markets = markets
                state.stats["discoveries"] += 1
                log(f"  discovered {len(markets)} markets / {len(tokens)} tokens")
            except Exception as e:
                log(f"  discovery err: {e}")
            for _ in range(MARKET_REFRESH_SEC):
                if not _running: break
                await asyncio.sleep(1)
    finally:
        http.close()


async def stats_loop(state):
    while _running:
        for _ in range(30):
            if not _running: break
            await asyncio.sleep(1)
        s = state.stats
        log(f"  STAT msgs={s['ws_msgs']} snap={s['snapshots']} delta={s['price_changes']} | detections={s['detections']} tradable={s['tradable_detections']} | books={len(state.books)} markets={len(state.markets)}")


async def main_async():
    signal.signal(signal.SIGINT, _sigint)
    state = ArbState()
    log(f"=== WS arb observer (PH local, observe-only) ===")
    log(f"  log threshold: sum<{LOG_THRESHOLD}, tradable<{TRADABLE_THRESHOLD}")
    log(f"  detection log: {DETECT_LOG}")
    # Initial discovery
    http = httpx.Client()
    tokens, markets = discover_markets(http)
    http.close()
    state.tokens = tokens
    state.markets = markets
    log(f"  initial: {len(markets)} markets / {len(tokens)} tokens")

    await asyncio.gather(
        ws_loop(state),
        discovery_loop(state),
        stats_loop(state),
    )


if __name__ == "__main__":
    asyncio.run(main_async())
