"""edge_probe.py — Real-time directional-lag probe (OBSERVE ONLY, no orders).

Quantifies how much the Polymarket *-updown-5m/15m order book LAGS the
underlying crypto price, i.e. the directional edge window.

Three data sources:
  1. Binance futures WS bookTicker  -> direction (price-discovery leader)
  2. Pyth Hermes SSE stream         -> cross-validation (basis check)
  3. Polymarket CLOB WS             -> implied Up/Down price (the laggard)

For each active market:
  underlying_chg = mid_now / open_ref - 1        (open_ref = Binance 1m open @ window start)
  winner         = "Up" if chg>=0 else "Down"    (what Chainlink would resolve, approx)
  winner_ask     = cost to BUY the winning side on Polymarket right now
  LAG/EDGE       = underlying clearly decided (|chg|>=MIN_CHG) but winner_ask still cheap

Note: resolution source is Chainlink BTC/USD data stream; Binance is used as a
near-identical proxy (basis ~0 except in the final coin-flip seconds, which we skip).

Logs every lag event to data/edge_probe.jsonl for offline analysis.
"""
import argparse, asyncio, json, os, signal, sys, time
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
# slug-asset -> (binance futures symbol, pyth feed id without 0x)
ASSETS = {
    "btc": ("BTCUSDT", "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"),
    "eth": ("ETHUSDT", "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace"),
    "sol": ("SOLUSDT", "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d"),
    "xrp": ("XRPUSDT", "ec5d399846a9209f3fe5881d70aae9268c94339ff9817e8d18ff19fa05eea1c8"),
}
SYM_TO_ASSET = {v[0]: k for k, v in ASSETS.items()}
PID_TO_ASSET = {v[1]: k for k, v in ASSETS.items()}

MIN_CHG_PCT = 0.05        # underlying considered "decided" beyond this move (below = noise zone)
CHEAP_WINNER = 0.85       # winner side ask below this while decided = lag/edge
MIN_TTL = 15              # ignore final coin-flip seconds
MAX_TTL_VIEW = 960        # only track markets settling within this horizon
REFRESH_SEC = 30
REPORT_SEC = 2

GAMMA = "https://gamma-api.polymarket.com/markets"
BINANCE_KLINE = "https://fapi.binance.com/fapi/v1/klines"
BINANCE_WS = "wss://fstream.binance.com/stream?streams="
PYTH_STREAM = "https://hermes.pyth.network/v2/updates/price/stream"
CLOB_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
LOG_FILE = os.path.join(DATA_DIR, "edge_probe.log")
EVENT_FILE = os.path.join(DATA_DIR, "edge_probe.jsonl")

_running = True
def _sigint(_s, _f):
    global _running; _running = False
signal.signal(signal.SIGINT, _sigint)

def now(): return time.time()
def iso(): return datetime.now(timezone.utc).strftime("%H:%M:%S")

def log(msg):
    line = f"[{iso()}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f: f.write(line + "\n")
    except: pass


# === Order book (reused from ws_arb_observer, proven) ===
class OrderBook:
    def __init__(self):
        self.asks = []   # (price,size) asc
        self.bids = []   # (price,size) desc
        self.last_update = 0
    def apply_snapshot(self, asks, bids):
        try:
            self.asks = sorted([(float(a["price"]), float(a["size"])) for a in asks])
            self.bids = sorted([(float(b["price"]), float(b["size"])) for b in bids], reverse=True)
        except: pass
        self.last_update = now()
    def apply_price_change(self, changes):
        for ch in changes:
            try:
                price = float(ch["price"]); size = float(ch["size"]); side = ch.get("side", "").upper()
            except: continue
            book = self.asks if side == "SELL" else self.bids
            book[:] = [(p, s) for (p, s) in book if abs(p - price) > 1e-9]
            if size > 0: book.append((price, size))
            if side == "SELL": self.asks = sorted(book)
            else: self.bids = sorted(book, reverse=True)
        self.last_update = now()
    def best_ask(self):
        for p, s in self.asks:
            if s > 0 and p < 1.0: return p
        return None
    def best_bid(self):
        for p, s in self.bids:
            if s > 0 and p > 0.0: return p
        return None


class State:
    def __init__(self):
        self.binance = {}            # asset -> (mid, ts)
        self.pyth = {}               # asset -> (price, ts)
        self.markets = {}            # slug -> {asset,start,end,mtype,up_tok,dn_tok,open_ref}
        self.books = defaultdict(OrderBook)   # token -> OrderBook
        self.tok2mkt = {}            # token -> (slug, "Up"/"Down")
        self.tokens_ver = 0
        self.active_tokens = []
        self.stats = defaultdict(int)


# === Binance futures WS ===
async def binance_ws(state):
    streams = "/".join(f"{ASSETS[a][0].lower()}@bookTicker" for a in ASSETS)
    url = BINANCE_WS + streams
    delay = 1
    while _running:
        try:
            async with websockets.connect(url, ping_interval=15, ping_timeout=15) as ws:
                log(f"  binance WS connected ({len(ASSETS)} symbols)")
                delay = 1
                while _running:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    m = json.loads(raw)
                    d = m.get("data", m)
                    sym = d.get("s")
                    asset = SYM_TO_ASSET.get(sym)
                    if not asset: continue
                    try:
                        bid = float(d["b"]); ask = float(d["a"])
                        state.binance[asset] = ((bid + ask) / 2.0, now())
                        state.stats["binance_ticks"] += 1
                    except: pass
        except Exception as e:
            if not _running: break
            log(f"  binance WS err: {e}; retry {delay}s")
            await asyncio.sleep(delay); delay = min(30, delay * 2)


# === Pyth Hermes SSE ===
async def pyth_sse(state):
    params = [("ids[]", "0x" + ASSETS[a][1]) for a in ASSETS]
    delay = 1
    while _running:
        try:
            async with httpx.AsyncClient(timeout=None) as cli:
                async with cli.stream("GET", PYTH_STREAM, params=params) as r:
                    log(f"  pyth SSE connected ({len(ASSETS)} feeds)")
                    delay = 1
                    async for line in r.aiter_lines():
                        if not _running: break
                        if not line.startswith("data:"): continue
                        try:
                            payload = json.loads(line[5:].strip())
                        except: continue
                        for pf in payload.get("parsed", []):
                            asset = PID_TO_ASSET.get(pf.get("id", ""))
                            if not asset: continue
                            pr = pf.get("price", {})
                            try:
                                val = int(pr["price"]) * (10 ** int(pr["expo"]))
                                state.pyth[asset] = (val, now())
                                state.stats["pyth_ticks"] += 1
                            except: pass
        except Exception as e:
            if not _running: break
            log(f"  pyth SSE err: {e}; retry {delay}s")
            await asyncio.sleep(delay); delay = min(30, delay * 2)


# === Discovery: build current/next-window slugs directly (gamma list buries live ones) ===
async def fetch_market(cli, slug, asset, mtype, dur, start):
    try:
        r = await cli.get(GAMMA, params={"slug": slug})
        arr = r.json()
        if not arr: return None
        m = arr[0]
        if m.get("closed"): return None
        ids = json.loads(m.get("clobTokenIds") or "[]")
        outs = json.loads(m.get("outcomes") or "[]")
        if len(ids) < 2 or len(outs) < 2: return None
        try:
            up_tok = ids[outs.index("Up")]; dn_tok = ids[outs.index("Down")]
        except ValueError:
            up_tok, dn_tok = ids[0], ids[1]
        return slug, {"asset": asset, "start": start, "end": start + dur, "mtype": mtype,
                      "up_tok": up_tok, "dn_tok": dn_tok, "open_ref": None}
    except Exception:
        return None


async def discovery(state):
    while _running:
        try:
            tnow = int(now())
            cands = []
            for asset in ASSETS:
                for mtype, dur in (("5m", 300), ("15m", 900)):
                    base = (tnow // dur) * dur
                    for start in (base, base + dur):   # current + next window
                        cands.append((f"{asset}-updown-{mtype}-{start}", asset, mtype, dur, start))
            async with httpx.AsyncClient(timeout=15) as cli:
                results = await asyncio.gather(*[fetch_market(cli, *c) for c in cands])
                cur = {}
                for res in results:
                    if not res: continue
                    slug, mk = res
                    ttl = mk["end"] - now()
                    if ttl < MIN_TTL or ttl > MAX_TTL_VIEW: continue
                    prev = state.markets.get(slug)
                    if prev and prev.get("open_ref") is not None:
                        mk["open_ref"] = prev["open_ref"]
                    cur[slug] = mk
                for slug, mk in cur.items():
                    if mk["open_ref"] is None:
                        mk["open_ref"] = await fetch_open_ref(cli, mk["asset"], mk["start"])
            state.markets = cur
            tok2mkt = {}
            for slug, mk in cur.items():
                tok2mkt[mk["up_tok"]] = (slug, "Up")
                tok2mkt[mk["dn_tok"]] = (slug, "Down")
            new_tokens = sorted(tok2mkt.keys())
            if new_tokens != state.active_tokens:
                state.active_tokens = new_tokens
                state.tok2mkt = tok2mkt
                state.tokens_ver += 1
            state.stats["discoveries"] += 1
            log(f"  discovered {len(cur)} live markets / {len(new_tokens)} tokens (ver {state.tokens_ver})")
        except Exception as e:
            log(f"  discovery err: {e}")
        for _ in range(REFRESH_SEC):
            if not _running: break
            await asyncio.sleep(1)


async def fetch_open_ref(cli, asset, start_ts):
    try:
        r = await cli.get(BINANCE_KLINE, params={"symbol": ASSETS[asset][0], "interval": "1m",
                                                 "startTime": start_ts * 1000, "limit": 1})
        k = r.json()
        if k: return float(k[0][1])   # open of the start-minute candle
    except: pass
    return None


# === Polymarket CLOB WS ===
async def clob_ws(state):
    delay = 1
    while _running:
        tokens = list(state.active_tokens)
        my_ver = state.tokens_ver
        if not tokens:
            await asyncio.sleep(1); continue
        try:
            async with websockets.connect(CLOB_WS, ping_interval=10, ping_timeout=10,
                                           max_size=8 * 1024 * 1024) as ws:
                await ws.send(json.dumps({"type": "MARKET", "assets_ids": tokens}))
                log(f"  clob WS subscribed {len(tokens)} tokens (ver {my_ver})")
                delay = 1
                while _running and state.tokens_ver == my_ver:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    except asyncio.TimeoutError:
                        continue
                    state.stats["clob_msgs"] += 1
                    try: msg = json.loads(raw)
                    except: continue
                    for m in (msg if isinstance(msg, list) else [msg]):
                        et = m.get("event_type") or m.get("type")
                        aid = m.get("asset_id") or m.get("market")
                        if not aid: continue
                        if et == "book":
                            state.books[aid].apply_snapshot(m.get("asks") or [], m.get("bids") or [])
                        elif et == "price_change":
                            ch = m.get("changes") or m.get("price_changes") or [m]
                            state.books[aid].apply_price_change(ch)
                if state.tokens_ver != my_ver:
                    log("  clob WS resubscribing (token set changed)")
        except Exception as e:
            if not _running: break
            log(f"  clob WS err: {e}; retry {delay}s")
            await asyncio.sleep(delay); delay = min(30, delay * 2)


# === Reporter ===
async def reporter(state):
    await asyncio.sleep(3)
    while _running:
        tnow = now()
        rows = []
        for slug, mk in sorted(state.markets.items(), key=lambda x: x[1]["end"]):
            asset = mk["asset"]
            b = state.binance.get(asset); p = state.pyth.get(asset)
            mid = b[0] if b else None
            open_ref = mk["open_ref"]
            ttl = int(mk["end"] - tnow)
            up_ask = state.books[mk["up_tok"]].best_ask()
            dn_ask = state.books[mk["dn_tok"]].best_ask()
            if mid is None or open_ref is None or ttl < MIN_TTL:
                continue
            chg = (mid / open_ref - 1.0) * 100.0
            winner = "Up" if chg >= 0 else "Down"
            winner_ask = up_ask if winner == "Up" else dn_ask
            # pyth basis check — must AGREE on direction for a signal to count
            basis = ""
            basis_agree = False
            if p and open_ref:
                pchg = (p[0] / open_ref - 1.0) * 100.0
                basis_agree = (pchg >= 0) == (chg >= 0)
                basis = f"{'OK' if basis_agree else 'DIVERGE'}({pchg:+.3f})"
            # Real lag requires: large-enough move, BOTH sources agree on direction,
            # and the winning side still cheap. Noise-zone divergence is filtered out.
            lag = (winner_ask is not None and abs(chg) >= MIN_CHG_PCT
                   and basis_agree and winner_ask < CHEAP_WINNER)
            rows.append((asset, mk["mtype"], ttl, chg, winner, basis, up_ask, dn_ask, winner_ask, lag))
            if lag:
                ev = {"ts": int(tnow), "slug": slug, "asset": asset, "mtype": mk["mtype"],
                      "ttl": ttl, "und_chg_pct": round(chg, 4), "winner": winner,
                      "winner_ask": winner_ask, "up_ask": up_ask, "dn_ask": dn_ask,
                      "pyth_basis": basis, "basis_agree": basis_agree, "mid": mid, "open_ref": open_ref}
                try:
                    with open(EVENT_FILE, "a", encoding="utf-8") as f: f.write(json.dumps(ev) + "\n")
                except: pass
                state.stats["lag_events"] += 1
        if rows:
            print(f"\n=== {iso()} | binance={state.stats['binance_ticks']} pyth={state.stats['pyth_ticks']} "
                  f"clob={state.stats['clob_msgs']} | LAG_events={state.stats['lag_events']} ===")
            print(f"{'asset':<5} {'t':<4} {'ttl':>4} {'und%':>8} {'win':<4} {'pyth_chk':<16} "
                  f"{'up_ask':>7} {'dn_ask':>7} {'win_ask':>7}  edge")
            for (a, mt, ttl, chg, w, basis, ua, da, wa, lag) in rows:
                uas = f"{ua:.3f}" if ua is not None else "  -  "
                das = f"{da:.3f}" if da is not None else "  -  "
                was = f"{wa:.3f}" if wa is not None else "  -  "
                flag = "  <== LAG/EDGE" if lag else ""
                print(f"{a:<5} {mt:<4} {ttl:>4} {chg:>+8.3f} {w:<4} {basis:<16} "
                      f"{uas:>7} {das:>7} {was:>7}{flag}")
        for _ in range(REPORT_SEC):
            if not _running: break
            await asyncio.sleep(1)


async def main():
    state = State()
    log("edge_probe start — OBSERVE ONLY, no orders")
    log(f"  assets={list(ASSETS)} MIN_CHG={MIN_CHG_PCT}% CHEAP_WINNER<{CHEAP_WINNER} MIN_TTL={MIN_TTL}s")
    await asyncio.gather(
        binance_ws(state), pyth_sse(state), discovery(state),
        clob_ws(state), reporter(state),
    )
    log("edge_probe stopped")


if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
