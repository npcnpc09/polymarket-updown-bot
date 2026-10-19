"""v8 MIRROR paper simulator with sum<0.95 arb filter.

Strategy: when eebde trades any BTC 5m/15m market we haven't checked,
fetch BOTH side orderbooks, compute sum(Up_entry + Down_entry).
If sum < 0.95: enter both legs (mirror MM-arb).
Else: skip.

Realistic slippage: walk-the-book + 1c aggressiveness per leg.
NO real money. Sim balance tracked in state file.
"""
import argparse, json, os, re, signal, sys, time, traceback
from collections import defaultdict
from datetime import datetime, timezone

import httpx

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError): pass

INITIAL_SIM_BALANCE = 76.0
TRADE_SIZE = 2.0
MIN_SHARES = 5.0
DAILY_LOSS_STOP = -20.0
EMERGENCY_FLOOR = 40.0
MAX_OPEN = 60   # need more open since pairs are 2x positions
MIN_TIME_LEFT_SEC = 60
SLIPPAGE_AGG_CENTS = 0.01
MIRROR_SUM_THRESHOLD = 0.95  # only enter pair if walked Up+Down sum below this

LEADER_ADDR = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
SLUG_PATTERNS = (
    "btc-updown-5m-", "btc-updown-15m-",
    "eth-updown-5m-", "eth-updown-15m-",
    "sol-updown-5m-", "sol-updown-15m-",
    "xrp-updown-5m-", "xrp-updown-15m-",
)

DATA_API = "https://data-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

STATE_DIR = r"."
SIM_STATE_FILE = os.path.join(STATE_DIR, "v7_paper_state.json")

_running = True
def _sigint(_s, _f):
    global _running; _running = False


def now_iso(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def now_ts(): return int(time.time())
def today_utc(): return datetime.now(timezone.utc).date().isoformat()


def log(msg): print(f"[{now_iso()}] {msg}", flush=True)


def settle_ts_from_slug(slug):
    if "-updown-15m-" in slug:
        try: return int(slug.rsplit("-", 1)[1]) + 15 * 60
        except: return None
    if "-updown-5m-" in slug:
        try: return int(slug.rsplit("-", 1)[1]) + 5 * 60
        except: return None
    return None


def load_pk_proxy():
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    sniper_path = os.path.join(here, "sniper_live_v2.py")
    with open(sniper_path, encoding='utf-8') as f: c = f.read()
    pk = re.search(r'PK\s*=\s*"(0x[0-9a-fA-F]+)"', c).group(1)
    proxy = re.search(r'PROXY\s*=\s*"(0x[0-9a-fA-F]+)"', c).group(1)
    return pk, proxy


def new_state():
    return {
        "sim_balance": INITIAL_SIM_BALANCE,
        "started": now_iso(),
        "started_balance": INITIAL_SIM_BALANCE,
        "open": [], "settled": [], "seen_tx": [], "daily_pnl": {},
        "processed_cids": [],  # cids we've already checked for arb
        "stats": {
            "leader_seen": 0, "filtered_slug": 0, "filtered_perpetual": 0,
            "filtered_old": 0, "skipped_cid_processed": 0,
            "no_market": 0, "no_book": 0, "no_liquidity": 0,
            "filtered_sum_too_high": 0,
            "skipped_max_open": 0, "skipped_daily": 0, "skipped_balance": 0,
            "skipped_emergency": 0,
            "pairs_entered": 0, "partial_legs_entered": 0,
            "copied": 0, "wins": 0, "losses": 0, "pnl": 0.0,
            "slippage_cents_total": 0.0, "slippage_n": 0,
            "sum_entry_total": 0.0, "sum_entry_n": 0,
        },
    }


def load_state():
    if not os.path.exists(SIM_STATE_FILE):
        log(f"NEW state ${INITIAL_SIM_BALANCE:.2f}")
        return new_state()
    with open(SIM_STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    base = new_state()
    for k, v in base.items():
        state.setdefault(k, v)
    for k, v in base["stats"].items():
        state["stats"].setdefault(k, v)
    log(f"LOADED bal=${state['sim_balance']:.2f} open={len(state['open'])} settled={len(state['settled'])} pnl=${state['stats']['pnl']:+.2f}")
    return state


def save_state(state):
    tmp = SIM_STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(state, f, indent=1)
    os.replace(tmp, SIM_STATE_FILE)


def today_pnl(state):
    return state["daily_pnl"].get(today_utc(), 0.0)


def record_pnl(state, delta):
    d = today_utc()
    state["daily_pnl"][d] = state["daily_pnl"].get(d, 0.0) + delta


def can_trade_today(state):
    return today_pnl(state) > DAILY_LOSS_STOP


def fetch_activity(http, addr):
    try:
        r = http.get(f"{DATA_API}/activity", params={"user": addr, "limit": 50}, timeout=15)
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        log(f"  activity err: {e}"); return []


def fetch_market(http, cid):
    try:
        r = http.get(f"{CLOB_API}/markets/{cid}", timeout=10)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        log(f"  market err: {e}"); return None


class MarketCache:
    def __init__(self): self.tokens = {}
    def get_tokens(self, cid, http):
        if cid in self.tokens: return self.tokens[cid]
        mk = fetch_market(http, cid)
        if not mk: return None
        toks = {}
        for t in mk.get("tokens", []):
            oc = t.get("outcome"); tid = str(t.get("token_id"))
            if oc in ("Up", "Down") and tid: toks[oc] = tid
        if len(toks) == 2:
            self.tokens[cid] = toks
            return toks
        return None


def walk_book(asks, target_usdc):
    asks_sorted = sorted([(float(a.price), float(a.size)) for a in asks])
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
    avg_price = total_cost / total_shares if total_shares > 0 else 0
    return avg_price, max_price, total_shares, total_cost, levels


def settle_due(state, http):
    now = now_ts()
    still_open = []
    for p in state["open"]:
        if not p.get("settle_ts") or now < p["settle_ts"] + 30:
            still_open.append(p); continue
        mk = fetch_market(http, p["cid"])
        if not mk:
            still_open.append(p); continue
        tokens = mk.get("tokens", [])
        if not tokens:
            still_open.append(p); continue
        winners_in = [t.get("winner") for t in tokens]
        if winners_in.count(True) != 1:
            still_open.append(p); continue
        my = next((t for t in tokens if str(t.get("token_id")) == p["token_id"]), None)
        if not my:
            still_open.append(p); continue
        won = my.get("winner") is True
        if won:
            payout = p["shares"] * 1.0
            pnl = payout - p["cost"]
            state["sim_balance"] += payout
            state["stats"]["wins"] += 1
        else:
            payout = 0; pnl = -p["cost"]
            state["stats"]["losses"] += 1
        state["stats"]["pnl"] += pnl
        record_pnl(state, pnl)
        p["result"] = "win" if won else "loss"; p["pnl"] = pnl; p["payout"] = payout
        p["settled_at"] = now_iso()
        state["settled"].append(p)
        log(f"  SETTLE {p['slug'][:30]} {p['outcome']:<4} -> {p['result']:<4} entry={p['order_price']:.3f} pair_id={p.get('pair_id','?')[:8]} pnl=${pnl:+.2f} bal=${state['sim_balance']:.2f}")
    state["open"] = still_open


def process_signal(state, http, client, market_cache, signal):
    """signal = (cid, slug, leader_ts, settle_ts) — try to enter a mirror pair."""
    cid = signal["cid"]; slug = signal["slug"]; settle_ts = signal["settle_ts"]
    stat = state["stats"]

    # Skip if already processed this cid (arb checked once per market)
    if cid in state["processed_cids"]:
        stat["skipped_cid_processed"] += 1; return
    state["processed_cids"].append(cid)
    state["processed_cids"] = state["processed_cids"][-2000:]

    # Check max_open
    if len(state["open"]) >= MAX_OPEN - 1:
        stat["skipped_max_open"] += 1; return

    # Get token IDs
    tokens = market_cache.get_tokens(cid, http)
    if not tokens:
        stat["no_market"] += 1; return

    # Fetch both orderbooks + walk
    walked = {}
    for oc, tid in tokens.items():
        try:
            ob = client.get_order_book(token_id=tid)
        except Exception:
            stat["no_book"] += 1; return
        if not ob.asks:
            stat["no_book"] += 1; return
        w = walk_book(ob.asks, TRADE_SIZE)
        if w is None:
            stat["no_liquidity"] += 1; return
        walked[oc] = w  # (avg, max_price, shares, cost, levels)

    # Compute effective entry per leg
    entry_up = min(0.99, round(walked["Up"][1] + SLIPPAGE_AGG_CENTS, 4))
    entry_dn = min(0.99, round(walked["Down"][1] + SLIPPAGE_AGG_CENTS, 4))
    sum_entry = entry_up + entry_dn

    stat["sum_entry_total"] += sum_entry; stat["sum_entry_n"] += 1

    if sum_entry >= MIRROR_SUM_THRESHOLD:
        stat["filtered_sum_too_high"] += 1
        return

    # Sizing per leg
    shares_up = max(MIN_SHARES, TRADE_SIZE / entry_up)
    shares_dn = max(MIN_SHARES, TRADE_SIZE / entry_dn)
    cost_up = round(shares_up * entry_up, 4)
    cost_dn = round(shares_dn * entry_dn, 4)
    total_cost = cost_up + cost_dn

    # Capital check
    if state["sim_balance"] < total_cost:
        stat["skipped_balance"] += 1; return

    # Emergency floor
    open_cost = sum(p["cost"] for p in state["open"])
    if state["sim_balance"] + open_cost - total_cost <= EMERGENCY_FLOOR:
        stat["skipped_emergency"] += 1; return

    # Check we don't already have either leg
    has_up = any(p["cid"] == cid and p["outcome"] == "Up" for p in state["open"])
    has_dn = any(p["cid"] == cid and p["outcome"] == "Down" for p in state["open"])
    if has_up and has_dn:
        return  # nothing to add

    pair_id = signal.get("tx", "")[:10]
    expected_payout = max(shares_up, shares_dn) * 1.0  # winner takes shares*$1
    locked_profit = expected_payout - total_cost

    # Enter both legs (if not already held)
    if not has_up:
        state["sim_balance"] -= cost_up
        pos = {
            "cid": cid, "token_id": tokens["Up"], "slug": slug, "outcome": "Up",
            "order_price": entry_up, "shares": shares_up, "cost": cost_up,
            "sum_entry": sum_entry, "expected_pair_profit": locked_profit,
            "settle_ts": settle_ts, "opened_at": now_iso(), "pair_id": pair_id,
        }
        state["open"].append(pos)
        stat["copied"] += 1
        stat["slippage_cents_total"] += entry_up * 100
        stat["slippage_n"] += 1
    if not has_dn:
        state["sim_balance"] -= cost_dn
        pos = {
            "cid": cid, "token_id": tokens["Down"], "slug": slug, "outcome": "Down",
            "order_price": entry_dn, "shares": shares_dn, "cost": cost_dn,
            "sum_entry": sum_entry, "expected_pair_profit": locked_profit,
            "settle_ts": settle_ts, "opened_at": now_iso(), "pair_id": pair_id,
        }
        state["open"].append(pos)
        stat["copied"] += 1
        stat["slippage_cents_total"] += entry_dn * 100
        stat["slippage_n"] += 1

    if not has_up and not has_dn:
        stat["pairs_entered"] += 1
    else:
        stat["partial_legs_entered"] += 1

    log(f"  PAIR {slug[:24]} Up={entry_up:.3f}/${cost_up:.2f} Down={entry_dn:.3f}/${cost_dn:.2f} SUM={sum_entry:.3f} locked=${locked_profit:+.2f} bal=${state['sim_balance']:.2f}")


def maybe_enter(state, http, client, market_cache):
    if not can_trade_today(state):
        state["stats"]["skipped_daily"] += 1; return

    acts = fetch_activity(http, LEADER_ADDR)
    if not acts: return
    acts.sort(key=lambda a: int(a.get("timestamp", 0) or 0))
    seen = set(state["seen_tx"])
    stat = state["stats"]

    for a in acts:
        tx = a.get("transactionHash")
        if not tx or tx in seen: continue
        seen.add(tx)
        ts_ev = int(a.get("timestamp", 0) or 0)
        if now_ts() - ts_ev > 120:
            stat["filtered_old"] += 1; continue
        if a.get("type") != "TRADE" or a.get("side") != "BUY": continue
        stat["leader_seen"] += 1
        slug = a.get("slug") or ""
        if not any(p in slug for p in SLUG_PATTERNS):
            stat["filtered_slug"] += 1; continue
        cid = a.get("conditionId")
        settle_ts = settle_ts_from_slug(slug)
        if settle_ts and (settle_ts - now_ts()) < MIN_TIME_LEFT_SEC:
            stat["filtered_perpetual"] += 1; continue

        process_signal(state, http, client, market_cache, {
            "cid": cid, "slug": slug, "settle_ts": settle_ts, "tx": tx,
        })

    state["seen_tx"] = list(seen)[-5000:]


def report(state):
    s = state["stats"]
    n_settled = s["wins"] + s["losses"]
    wr = s["wins"]/n_settled*100 if n_settled else 0
    open_cost = sum(p["cost"] for p in state["open"])
    total = state["sim_balance"] + open_cost
    delta = total - state.get("started_balance", INITIAL_SIM_BALANCE)
    settled_cost = sum(p["cost"] for p in state["settled"])
    roi = s["pnl"]/max(settled_cost,1)*100 if n_settled else 0
    avg_sum = s["sum_entry_total"]/s["sum_entry_n"] if s["sum_entry_n"] else 0
    log(f"  STAT bal=${state['sim_balance']:.2f} open={len(state['open'])} (${open_cost:.2f}) total=${total:.2f} delta=${delta:+.2f} | pairs={s['pairs_entered']} legs={s['copied']} settled={n_settled} WR={wr:.1f}% PnL=${s['pnl']:+.2f} ROI={roi:+.2f}% today=${today_pnl(state):+.2f} | avg_sum_entry={avg_sum:.3f} sum_too_high={s['filtered_sum_too_high']}/{s['sum_entry_n']} | seen={s['leader_seen']} slug={s['filtered_slug']} perp={s['filtered_perpetual']} no_mk={s['no_market']} no_book={s['no_book']} no_liq={s['no_liquidity']}")


def main():
    global _running
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=10)
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    signal.signal(signal.SIGINT, _sigint)

    log(f"=== v8 MIRROR paper simulator (arb-filter) ===")
    log(f"  start sim_balance: ${INITIAL_SIM_BALANCE:.2f}")
    log(f"  leader: eebde / Bonereaper")
    log(f"  filter: btc/eth/sol/xrp-(5m|15m), mirror both sides, sum<{MIRROR_SUM_THRESHOLD}")
    log(f"  trade_size per leg: ${TRADE_SIZE}, max_open: {MAX_OPEN}")
    log(f"  daily_stop: ${DAILY_LOSS_STOP}, emergency_floor: ${EMERGENCY_FLOOR}")

    if args.fresh and os.path.exists(SIM_STATE_FILE):
        os.remove(SIM_STATE_FILE); log("  fresh: state deleted")

    state = load_state()
    from polymarket import SecureClient
    pk, proxy = load_pk_proxy()
    client = SecureClient.create(private_key=pk, wallet=proxy)
    market_cache = MarketCache()
    http = httpx.Client()
    try:
        while _running:
            try: settle_due(state, http)
            except Exception as e: log(f"  settle err: {e}")
            try: maybe_enter(state, http, client, market_cache)
            except Exception as e: log(f"  enter err: {e}\n{traceback.format_exc()[:500]}")
            report(state)
            save_state(state)
            for _ in range(args.interval):
                if not _running: break
                time.sleep(1)
    finally:
        save_state(state); http.close(); log("=== shutdown ===")


if __name__ == "__main__":
    main()
