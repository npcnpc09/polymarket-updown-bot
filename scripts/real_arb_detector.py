"""real_arb_detector.py — Liquidity-gated TRUE arb detector (OBSERVE ONLY, no orders).

Answers the binding question: how often does a REAL, capturable arb appear on
deep books, and would our ~700ms post latency catch it?

Difference vs the old ws_arb_observer (which counted phantoms):
  * Walks both legs by SHARES (matches the real 5+5 buy), returns blended avg price.
  * LIQUIDITY GATE: an arb counts only if BOTH legs can actually fill N shares
    below $1 -- thin/phantom levels that can't fill N are rejected.
  * Tracks each arb as an EPISODE: when it opens, its min sum, its $depth, and how
    long it PERSISTS. An episode shorter than the latency budget is uncapturable
    (a phantom you can see but never hit).

Metrics (per asset): real-arb episodes/hr, median persistence, capturable rate
(duration >= --latency-ms), sum & depth distributions.

Output: data/real_arb_episodes.jsonl + periodic console report.
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

ASSETS = ("btc", "eth", "sol", "xrp")
N_SHARES = 5.0            # walk this many shares per leg (matches real buy size)
ARB_THRESHOLD = 1.00     # blended up_avg + dn_avg below this = free-profit arb
LATENCY_MS = 700         # our current post latency; episodes shorter = uncapturable
MIN_TTL = 30
MAX_TTL = 960
REFRESH_SEC = 30
REPORT_SEC = 15

GAMMA = "https://gamma-api.polymarket.com/markets"
CLOB_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data"); os.makedirs(DATA_DIR, exist_ok=True)
LOG_FILE = os.path.join(DATA_DIR, "real_arb_detector.log")
EP_FILE = os.path.join(DATA_DIR, "real_arb_episodes.jsonl")

_running = True
def _sigint(_s, _f):
    global _running; _running = False
signal.signal(signal.SIGINT, _sigint)

def now(): return time.time()
def iso(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def log(m):
    line = f"[{iso()}] {m}"; print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f: f.write(line + "\n")
    except: pass


class OrderBook:
    def __init__(self):
        self.asks = []; self.bids = []; self.last_update = 0
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
    def walk_shares(self, n):
        """blended avg price to BUY n shares from asks (price<1). None if not enough depth."""
        remaining = n; cost = 0.0; filled = 0.0
        for price, size in self.asks:
            if price >= 1.0: break
            take = min(remaining, size)
            cost += take * price; filled += take; remaining -= take
            if remaining <= 1e-9: break
        if filled < n - 1e-9: return None
        return cost / n
    def takeable_usd(self):
        return sum(p * s for p, s in self.asks if 0 < p < 1.0 and s > 0)


class State:
    def __init__(self):
        self.books = defaultdict(OrderBook)
        self.tok2mkt = {}      # token -> {slug, side, paired, asset, settle}
        self.markets = {}      # slug -> meta
        self.episodes = {}     # slug -> open episode dict (or absent)
        self.closed = []       # finished episodes
        self.active_tokens = []
        self.tokens_ver = 0
        self.stats = defaultdict(int)

    def evaluate(self, token, n_shares, threshold):
        meta = self.tok2mkt.get(token)
        if not meta: return
        slug = meta["slug"]; paired = meta["paired"]
        if paired not in self.books: return
        # order legs as Up/Down deterministically
        if meta["side"] == "Up":
            b_up, b_dn = self.books[token], self.books[paired]
        else:
            b_up, b_dn = self.books[paired], self.books[token]
        up_avg = b_up.walk_shares(n_shares)
        dn_avg = b_dn.walk_shares(n_shares)
        # LIQUIDITY GATE: both legs must fill n shares below $1
        is_arb = (up_avg is not None and dn_avg is not None and (up_avg + dn_avg) < threshold)
        eff_sum = (up_avg + dn_avg) if (up_avg is not None and dn_avg is not None) else None
        t = now()
        ep = self.episodes.get(slug)
        if is_arb:
            depth = min(b_up.takeable_usd(), b_dn.takeable_usd())
            if ep is None:
                self.episodes[slug] = {"slug": slug, "asset": meta["asset"], "open": t,
                                       "min_sum": eff_sum, "max_depth": depth, "samples": 1}
                self.stats["episodes_opened"] += 1
            else:
                ep["min_sum"] = min(ep["min_sum"], eff_sum)
                ep["max_depth"] = max(ep["max_depth"], depth)
                ep["samples"] += 1
        else:
            if ep is not None:
                self.close_episode(slug, t)

    def close_episode(self, slug, t):
        ep = self.episodes.pop(slug, None)
        if not ep: return
        dur_ms = (t - ep["open"]) * 1000.0
        rec = {"ts": int(ep["open"]), "slug": slug, "asset": ep["asset"],
               "min_sum": round(ep["min_sum"], 4), "depth_usd": round(ep["max_depth"], 2),
               "dur_ms": round(dur_ms), "samples": ep["samples"]}
        self.closed.append(rec)
        try:
            with open(EP_FILE, "a", encoding="utf-8") as f: f.write(json.dumps(rec) + "\n")
        except: pass
        self.stats["episodes_closed"] += 1


async def fetch_market(cli, slug, asset, mtype, dur, start):
    try:
        arr = (await cli.get(GAMMA, params={"slug": slug})).json()
        if not arr or arr[0].get("closed"): return None
        m = arr[0]
        ids = json.loads(m.get("clobTokenIds") or "[]")
        outs = json.loads(m.get("outcomes") or "[]")
        if len(ids) < 2 or "Up" not in outs or "Down" not in outs: return None
        up = ids[outs.index("Up")]; dn = ids[outs.index("Down")]
        return slug, {"asset": asset, "start": start, "settle": start + dur,
                      "up_tok": up, "dn_tok": dn}
    except Exception:
        return None


async def discovery(state):
    while _running:
        try:
            tnow = int(now()); cands = []
            for asset in ASSETS:
                for mtype, dur in (("5m", 300), ("15m", 900)):
                    base = (tnow // dur) * dur
                    for start in (base, base + dur):
                        cands.append((f"{asset}-updown-{mtype}-{start}", asset, mtype, dur, start))
            async with httpx.AsyncClient(timeout=15) as cli:
                res = await asyncio.gather(*[fetch_market(cli, *c) for c in cands])
            cur = {}
            for r in res:
                if not r: continue
                slug, mk = r
                ttl = mk["settle"] - now()
                if ttl < MIN_TTL or ttl > MAX_TTL: continue
                cur[slug] = mk
            # close episodes for markets that left the active set
            for slug in list(state.episodes.keys()):
                if slug not in cur: state.close_episode(slug, now())
            state.markets = cur
            tok2mkt = {}
            for slug, mk in cur.items():
                tok2mkt[mk["up_tok"]] = {"slug": slug, "side": "Up", "paired": mk["dn_tok"], "asset": mk["asset"], "settle": mk["settle"]}
                tok2mkt[mk["dn_tok"]] = {"slug": slug, "side": "Down", "paired": mk["up_tok"], "asset": mk["asset"], "settle": mk["settle"]}
            new_tokens = sorted(tok2mkt.keys())
            if new_tokens != state.active_tokens:
                state.active_tokens = new_tokens; state.tok2mkt = tok2mkt; state.tokens_ver += 1
            state.stats["discoveries"] += 1
            log(f"  discovered {len(cur)} live markets / {len(new_tokens)} tokens (ver {state.tokens_ver})")
        except Exception as e:
            log(f"  discovery err: {e}")
        for _ in range(REFRESH_SEC):
            if not _running: break
            await asyncio.sleep(1)


async def clob_ws(state, args):
    delay = 1
    while _running:
        tokens = list(state.active_tokens); my_ver = state.tokens_ver
        if not tokens: await asyncio.sleep(1); continue
        try:
            async with websockets.connect(CLOB_WS, ping_interval=10, ping_timeout=10, max_size=8*1024*1024) as ws:
                await ws.send(json.dumps({"type": "MARKET", "assets_ids": tokens}))
                log(f"  clob WS subscribed {len(tokens)} tokens (ver {my_ver})")
                delay = 1
                while _running and state.tokens_ver == my_ver:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    except asyncio.TimeoutError:
                        continue
                    state.stats["ws_msgs"] += 1
                    try: msg = json.loads(raw)
                    except: continue
                    for m in (msg if isinstance(msg, list) else [msg]):
                        et = m.get("event_type") or m.get("type")
                        aid = m.get("asset_id") or m.get("market")
                        if not aid: continue
                        if et == "book":
                            state.books[aid].apply_snapshot(m.get("asks") or [], m.get("bids") or [])
                            state.evaluate(aid, args.shares, args.threshold)
                        elif et == "price_change":
                            ch = m.get("changes") or m.get("price_changes") or [m]
                            state.books[aid].apply_price_change(ch)
                            state.evaluate(aid, args.shares, args.threshold)
        except Exception as e:
            if not _running: break
            log(f"  clob WS err: {e}; retry {delay}s")
            await asyncio.sleep(delay); delay = min(30, delay * 2)


async def reporter(state, args):
    await asyncio.sleep(REPORT_SEC)
    while _running:
        c = state.closed
        n = len(c)
        if n:
            by = defaultdict(lambda: [0, 0, []])   # asset -> [count, capturable, durations]
            for e in c:
                a = by[e["asset"]]; a[0] += 1
                if e["dur_ms"] >= args.latency_ms and e["depth_usd"] >= args.shares: a[1] += 1
                a[2].append(e["dur_ms"])
            durs = sorted(e["dur_ms"] for e in c)
            med = durs[len(durs)//2]
            cap = sum(1 for e in c if e["dur_ms"] >= args.latency_ms and e["depth_usd"] >= args.shares)
            deep = [e for e in c if e["asset"] in ("btc", "eth")]
            print(f"\n=== {iso()} | real-arb episodes (N={args.shares}sh sum<{args.threshold}) | ws_msgs={state.stats['ws_msgs']} ===")
            print(f"  TOTAL episodes={n}  capturable(dur>={args.latency_ms}ms & depth>=${args.shares})={cap} ({100*cap//max(n,1)}%)")
            print(f"  median duration={med}ms   open_now={len(state.episodes)}")
            print(f"  {'asset':<5} {'episodes':>8} {'capturable':>10} {'med_dur_ms':>10}")
            for a in ASSETS:
                if a in by:
                    cnt, capa, ds = by[a]
                    md = sorted(ds)[len(ds)//2] if ds else 0
                    print(f"  {a:<5} {cnt:>8} {capa:>10} {md:>10}")
        else:
            print(f"\n=== {iso()} | no real arb episode yet (gate: both legs fill {args.shares}sh, sum<{args.threshold}) | ws_msgs={state.stats['ws_msgs']} ===")
        for _ in range(REPORT_SEC):
            if not _running: break
            await asyncio.sleep(1)


async def main(args):
    state = State()
    log(f"real_arb_detector — OBSERVE ONLY | shares={args.shares} threshold={args.threshold} latency_budget={args.latency_ms}ms")
    await asyncio.gather(discovery(state), clob_ws(state, args), reporter(state, args))
    log("stopped")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--shares", type=float, default=N_SHARES)
    ap.add_argument("--threshold", type=float, default=ARB_THRESHOLD)
    ap.add_argument("--latency-ms", type=float, default=LATENCY_MS)
    a = ap.parse_args()
    try: asyncio.run(main(a))
    except KeyboardInterrupt: pass
