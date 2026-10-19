"""Phase 1 arb scanner — OBSERVE ONLY (no trading).

Continuously scan all active BTC/ETH/SOL/XRP 5m+15m Up/Down markets.
For each: compute walk-the-book sum(Up_entry + Down_entry).
Log every arb opportunity with full snapshot.

Usage:
    python arb_scanner_observe.py [--interval 5]

Outputs:
    D:\\polymarket_state\\arb_scanner.log         (line-per-cycle status)
    D:\\polymarket_state\\arb_opportunities.jsonl (one JSON per detected arb)
"""
import argparse, json, os, re, signal, sys, time
from datetime import datetime, timezone
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import httpx

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError): pass

ASSETS = ("bitcoin", "ethereum", "solana", "xrp")  # title keywords
SLUG_PATTERNS = ("btc-updown-5m-", "btc-updown-15m-",
                 "eth-updown-5m-", "eth-updown-15m-",
                 "sol-updown-5m-", "sol-updown-15m-",
                 "xrp-updown-5m-", "xrp-updown-15m-")

TARGET_USDC = 2.0
LOG_THRESHOLD = 1.05   # log all sums < this for spread distribution analysis
TRADE_THRESHOLD = 0.95  # mark "tradable" flag (real edge)
MIN_TIME_LEFT_SEC = 30

STATE_DIR = r"."
SCANNER_LOG = os.path.join(STATE_DIR, "arb_scanner.log")
ARB_LOG = os.path.join(STATE_DIR, "arb_opportunities.jsonl")

_running = True
def _sigint(_s, _f):
    global _running; _running = False


def now_iso(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def now_ts(): return int(time.time())


def log(msg):
    line = f"[{now_iso()}] {msg}"
    print(line, flush=True)
    try:
        with open(SCANNER_LOG, "a", encoding="utf-8") as f: f.write(line + "\n")
    except: pass


def settle_ts_from_slug(slug):
    if "-updown-15m-" in slug:
        try: return int(slug.rsplit("-", 1)[1]) + 15 * 60
        except: return None
    if "-updown-5m-" in slug:
        try: return int(slug.rsplit("-", 1)[1]) + 5 * 60
        except: return None
    return None


ASSET_SLUGS = ("btc", "eth", "sol", "xrp")
def fetch_active_markets(http):
    """Deterministically query current+upcoming 5m+15m markets per asset."""
    now = now_ts()
    slot5 = now // 300 * 300
    slot15 = now // 900 * 900
    candidate_slugs = []
    for asset in ASSET_SLUGS:
        # 5m: current slot + next 2
        for s in (slot5, slot5+300, slot5+600):
            if s + 300 > now: candidate_slugs.append(f"{asset}-updown-5m-{s}")
        # 15m: current + next
        for s in (slot15, slot15+900):
            if s + 900 > now: candidate_slugs.append(f"{asset}-updown-15m-{s}")

    events = []
    for slug in candidate_slugs:
        try:
            r = http.get("https://gamma-api.polymarket.com/events",
                         params={"slug": slug}, timeout=10)
            if r.status_code != 200: continue
            data = r.json()
            if data: events.extend(data)
        except Exception:
            continue
    return events


def walk_book(asks, target_usdc):
    asks_sorted = sorted([(float(a["price"]), float(a["size"])) for a in asks])
    remaining = target_usdc
    total_shares = 0.0; total_cost = 0.0; max_price = 0.0; levels = 0
    for price, size in asks_sorted:
        if remaining <= 0: break
        if price >= 1.0: continue
        usdc_at_level = price * size
        take = min(remaining, usdc_at_level)
        shares_at_level = take / price
        total_shares += shares_at_level
        total_cost += take
        remaining -= take
        max_price = price; levels += 1
    if remaining > 0.01: return None
    avg = total_cost / total_shares if total_shares > 0 else 0
    return {"avg": avg, "max": max_price, "shares": total_shares, "cost": total_cost, "levels": levels}


def fetch_orderbook(http, token_id):
    try:
        r = http.get(f"https://clob.polymarket.com/book", params={"token_id": token_id}, timeout=10)
        if r.status_code != 200: return None
        return r.json()
    except: return None


def extract_markets_from_events(events):
    """Find all up/down markets matching our slug patterns."""
    found = {}  # cid -> {slug, up_token, down_token, settle_ts}
    for ev in events:
        ev_slug = ev.get("slug") or ""
        # Check if matches any pattern (event level or market level)
        for market in ev.get("markets", []):
            if market.get("closed"): continue
            m_slug = market.get("slug", ev_slug)
            if not any(p in m_slug for p in SLUG_PATTERNS): continue
            try:
                outcomes = market.get("outcomes")
                if isinstance(outcomes, str): outcomes = json.loads(outcomes)
                tokens = market.get("clobTokenIds")
                if isinstance(tokens, str): tokens = json.loads(tokens)
                if not ("Up" in outcomes and "Down" in outcomes): continue
                up_idx = outcomes.index("Up"); dn_idx = outcomes.index("Down")
                cid = market.get("conditionId", "")
                settle = settle_ts_from_slug(m_slug)
                if not settle or settle - now_ts() < MIN_TIME_LEFT_SEC: continue
                if cid in found: continue
                found[cid] = {
                    "slug": m_slug, "cid": cid,
                    "up_token": str(tokens[up_idx]), "down_token": str(tokens[dn_idx]),
                    "settle_ts": settle,
                }
            except Exception as e:
                continue
    return found


def fetch_pair_books(http, m):
    """Fetch both Up/Down orderbooks for one market."""
    ob_up = fetch_orderbook(http, m["up_token"])
    ob_dn = fetch_orderbook(http, m["down_token"])
    return m, ob_up, ob_dn


def scan_cycle(http, stats, executor):
    """One scan cycle: discover markets, compute arb for each (parallel)."""
    events = fetch_active_markets(http)
    markets = extract_markets_from_events(events)
    stats["scans"] += 1
    stats["markets_total_seen"] = len(markets)

    arbs_found = []
    # Parallel fetch both orderbooks per market
    futures = [executor.submit(fetch_pair_books, http, m) for m in markets.values()]
    for fut in futures:
        try:
            m, ob_up, ob_dn = fut.result(timeout=8)
        except Exception:
            continue
        if not ob_up or not ob_dn: continue
        asks_up = ob_up.get("asks") or []
        asks_dn = ob_dn.get("asks") or []
        if not asks_up or not asks_dn: continue
        w_up = walk_book(asks_up, TARGET_USDC)
        w_dn = walk_book(asks_dn, TARGET_USDC)
        if not w_up or not w_dn: continue

        entry_up = round(min(0.99, w_up["max"] + 0.01), 4)
        entry_dn = round(min(0.99, w_dn["max"] + 0.01), 4)
        sum_entry = entry_up + entry_dn
        sum_raw = w_up["max"] + w_dn["max"]

        if sum_entry < LOG_THRESHOLD:
            tradable = sum_entry < TRADE_THRESHOLD
            arb = {
                "ts": now_ts(), "iso": now_iso(),
                "cid": m["cid"], "slug": m["slug"],
                "settle_ts": m["settle_ts"],
                "time_to_settle": m["settle_ts"] - now_ts(),
                "raw_sum": round(sum_raw, 4),
                "eff_sum": round(sum_entry, 4),
                "up_entry": entry_up, "down_entry": entry_dn,
                "up_levels": w_up["levels"], "down_levels": w_dn["levels"],
                "locked_profit_per_share": round(1.0 - sum_entry, 4),
                "tradable": tradable,
            }
            arbs_found.append(arb)
            stats["arbs_logged_total"] += 1
            if tradable: stats["arbs_tradable_total"] += 1

            with open(ARB_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(arb) + "\n")

    return len(markets), arbs_found


def main():
    global _running
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=8)
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _sigint)

    log(f"=== ARB SCANNER (observe-only) ===")
    log(f"  scan interval: {args.interval}s")
    log(f"  log all sum < {LOG_THRESHOLD}, mark tradable if sum < {TRADE_THRESHOLD}")
    log(f"  patterns: {SLUG_PATTERNS}")
    log(f"  log file: {ARB_LOG}")

    stats = {"scans": 0, "markets_total_seen": 0,
             "arbs_logged_total": 0, "arbs_tradable_total": 0}

    http = httpx.Client()
    executor = ThreadPoolExecutor(max_workers=16)
    try:
        while _running:
            t0 = time.time()
            try:
                n_mk, arbs = scan_cycle(http, stats, executor)
                cycle_ms = (time.time() - t0) * 1000
                tradable_now = sum(1 for a in arbs if a["tradable"])
                if arbs:
                    best = min(arbs, key=lambda a: a["eff_sum"])
                    log(f"  scan #{stats['scans']} mk={n_mk} arbs={len(arbs)} (tradable={tradable_now}) | best={best['slug'][:24]} sum={best['eff_sum']:.3f} profit_per_share={best['locked_profit_per_share']:+.3f} | cumul logged={stats['arbs_logged_total']} trad={stats['arbs_tradable_total']} | {cycle_ms:.0f}ms")
                else:
                    log(f"  scan #{stats['scans']} mk={n_mk} arbs=0 | {cycle_ms:.0f}ms")
            except Exception as e:
                log(f"  scan err: {e}")
            for _ in range(args.interval):
                if not _running: break
                time.sleep(1)
    finally:
        executor.shutdown(wait=False)
        http.close()
        log(f"=== shutdown — total scans={stats['scans']} arbs={stats['arbs_logged_total']} tradable={stats['arbs_tradable_total']} ===")


if __name__ == "__main__":
    main()
