"""fill_rate_test.py — Measure REAL two-leg fill rate (half-leg rate) on Polymarket.

The ONLY experiment paper can't answer: when you batch-post both legs of an arb,
does the cheap leg ACTUALLY fill, or do you get left half-legged?

Design (safety first):
  * BTC only (deep book — avoids SOL/ETH phantom-liquidity false arbs).
  * Enter only when up_ask + dn_ask <= MAX_ENTER_SUM (<=1.00 default), so if BOTH
    legs fill you own Up+Down = redeem $1 ~ breakeven. The ONLY real downside is a
    half-leg, which is precisely what we measure.
  * BUY limit placed AT the displayed ask -> directly tests if that ask is real.
  * Batch post both legs simultaneously (post_orders) = fastest, fairest test.
  * Half-leg -> cancel the unfilled leg + market-FAK-sell the filled leg to flatten.
  * Hard caps: MAX_TRIALS, SIZE_SHARES, MAX_SPEND_USD.

DRY RUN:  python fill_rate_test.py --dry          (no orders; no creds needed)
REAL:     set POLY_PK / POLY_PROXY, then:
          python fill_rate_test.py --trials 3     (REAL MONEY)

Output: data/fill_rate_test.jsonl  + console summary (half-leg rate).
"""
import argparse, json, os, sys, threading, time
from collections import deque
from datetime import datetime, timezone

import httpx

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except: pass

# === Safety caps (defaults; some overridable via CLI) ===
ASSET = "btc"
SIZE_SHARES = 5.0          # Polymarket minimum; ~ $0.5-3.5 / leg depending on price
MAX_TRIALS = 3
MAX_SPEND_USD = 20.0       # hard cumulative cost ceiling -> abort
MAX_ENTER_SUM = 1.00       # only enter when up_ask+dn_ask <= this (hedged worst case)
MIN_TTL = 90               # need time to observe + unwind
MAX_TTL = 280              # not too close to settle
FILL_WAIT_SEC = 4.0        # poll fills for this long after posting
POLL_EVERY = 0.25

GAMMA = "https://gamma-api.polymarket.com/markets"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
EVENT_FILE = os.path.join(DATA_DIR, "fill_rate_test.jsonl")


def iso(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def log(m): print(f"[{iso()}] {m}", flush=True)


class VolMonitor:
    """Background BTC futures price poller -> short-term volatility in bps."""
    def __init__(self, window_sec=20):
        self.window = window_sec
        self.pts = deque()   # (ts, price)
        self._run = True
        self._t = threading.Thread(target=self._loop, daemon=True)
    def start(self): self._t.start(); return self
    def stop(self): self._run = False
    def _loop(self):
        c = httpx.Client(timeout=5)
        while self._run:
            try:
                r = c.get("https://fapi.binance.com/fapi/v1/ticker/price",
                          params={"symbol": "BTCUSDT"})
                px = float(r.json()["price"])
                now = time.time()
                self.pts.append((now, px))
                while self.pts and now - self.pts[0][0] > self.window:
                    self.pts.popleft()
            except Exception:
                pass
            time.sleep(0.8)
    def vol_bps(self):
        if len(self.pts) < 3: return None
        prices = [p for _, p in self.pts]
        mean = sum(prices) / len(prices)
        if mean <= 0: return None
        return (max(prices) - min(prices)) / mean * 1e4
    def last_px(self):
        return self.pts[-1][1] if self.pts else None


def load_env():
    envf = os.path.join(ROOT, ".env")
    if os.path.exists(envf):
        for line in open(envf, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    return os.environ.get("POLY_PK"), os.environ.get("POLY_PROXY")


def current_btc_window():
    """Return (slug, start, end, ttl) for the current BTC 5m window."""
    tnow = int(time.time())
    start = (tnow // 300) * 300
    return f"{ASSET}-updown-5m-{start}", start, start + 300, start + 300 - tnow


def fetch_market(http, slug):
    arr = http.get(GAMMA, params={"slug": slug}, timeout=10).json()
    if not arr: return None
    m = arr[0]
    if m.get("closed"): return None
    ids = json.loads(m.get("clobTokenIds") or "[]")
    outs = json.loads(m.get("outcomes") or "[]")
    if len(ids) < 2 or "Up" not in outs or "Down" not in outs: return None
    return {"slug": slug, "cond": m.get("conditionId"),
            "up_tok": ids[outs.index("Up")], "dn_tok": ids[outs.index("Down")]}


def best_ask_rest(http, token_id):
    """(price, size) of the cheapest real ask via CLOB REST."""
    b = http.get("https://clob.polymarket.com/book", params={"token_id": token_id}, timeout=10).json()
    asks = sorted((float(a["price"]), float(a["size"])) for a in b.get("asks", []))
    for p, s in asks:
        if s > 0 and p < 1.0:
            return p, s
    return None, None


def record(ev):
    with open(EVENT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(ev) + "\n")


def classify_post(resp):
    """resp: AcceptedOrder|RejectedOrder -> (ok, order_id, status, filled_shares)."""
    ok = getattr(resp, "ok", False)
    if not ok:
        return False, None, getattr(resp, "code", "rejected"), 0.0
    oid = getattr(resp, "order_id", None)
    status = getattr(resp, "status", "?")
    taking = getattr(resp, "taking_amount", None)   # shares received on BUY
    filled = float(taking) if taking is not None else (SIZE_SHARES if status == "matched" else 0.0)
    return True, oid, status, filled


def run_real(pk, proxy, args):
    from polymarket import SecureClient
    log("creating SecureClient (real money mode)...")
    client = SecureClient.create(private_key=pk, wallet=proxy)
    bal = client.get_balance_allowance(asset_type="COLLATERAL")
    usdc = float(bal.balance) / 1e6
    log(f"  wallet USDC = ${usdc:.2f}")
    if usdc < 6:
        log("  balance too low (<$6); abort."); return
    http = httpx.Client()
    vm = VolMonitor().start()
    if args.min_vol_bps > 0:
        log(f"  VOLATILITY GATE: only enter when BTC 20s vol >= {args.min_vol_bps} bps")
        time.sleep(6)   # let monitor warm up
    results = []
    spent = 0.0
    net_loss = 0.0
    done_windows = set()
    hb = [0]

    trial = 0
    while trial < args.trials:
        slug, start, end, ttl = current_btc_window()
        if slug in done_windows:
            time.sleep(2)
            if time.time() > end: continue
            continue
        if not (MIN_TTL <= ttl <= MAX_TTL):
            time.sleep(3); continue
        # EARLY volatility gate: during calm, skip cheaply (no book fetches / no log spam)
        if args.min_vol_bps > 0:
            vb = vm.vol_bps()
            if vb is None or vb < args.min_vol_bps:
                hb[0] += 1
                if hb[0] % 30 == 0:
                    msg = f"vol={vb:.1f}bps" if vb is not None else "warming"
                    log(f"  ...calm ({msg}); waiting for >= {args.min_vol_bps}bps | trials {trial}/{args.trials} net~${net_loss:.2f}")
                time.sleep(2); continue
        try:
            mk = fetch_market(http, slug)
            if not mk:
                time.sleep(2); continue
            # live book via SDK (authoritative)
            ob_up = client.get_order_book(token_id=mk["up_tok"])
            ob_dn = client.get_order_book(token_id=mk["dn_tok"])
        except Exception as e:
            log(f"  read error: {e}; retry in 3s"); time.sleep(3); continue
        ua = next(((float(l.price), float(l.size)) for l in sorted(ob_up.asks, key=lambda x: float(x.price)) if float(l.size) > 0 and float(l.price) < 1), (None, None))
        da = next(((float(l.price), float(l.size)) for l in sorted(ob_dn.asks, key=lambda x: float(x.price)) if float(l.size) > 0 and float(l.price) < 1), (None, None))
        up_ask, up_sz = ua; dn_ask, dn_sz = da
        tick = float(getattr(ob_up, "tick_size", 0.01) or 0.01)
        if up_ask is None or dn_ask is None:
            log("  missing ask side; skip"); time.sleep(2); continue
        ssum = up_ask + dn_ask
        vbps = vm.vol_bps()
        vstr = f"{vbps:.1f}bps" if vbps is not None else "?"
        log(f"  {slug} ttl={ttl}s  up_ask={up_ask:.3f}(x{up_sz:.0f}) dn_ask={dn_ask:.3f}(x{dn_sz:.0f}) sum={ssum:.3f} vol={vstr}")
        if ssum > args.max_sum:
            log(f"  sum {ssum:.3f} > max_enter {args.max_sum}; skip (no safe entry)"); time.sleep(3); continue
        if args.min_vol_bps > 0 and (vbps is None or vbps < args.min_vol_bps):
            log(f"  vol {vstr} < gate {args.min_vol_bps}bps; waiting for volatility..."); time.sleep(2); continue
        if net_loss >= args.max_net_loss:
            log(f"  est net loss ${net_loss:.2f} >= cap ${args.max_net_loss}; stop."); break

        # --- place BOTH legs at the displayed ask (marketable BUY) ---
        done_windows.add(slug)
        log(f"  TRIAL {trial+1}: BUY Up @ {up_ask:.3f} x{args.size} + BUY Down @ {dn_ask:.3f} x{args.size}  (vol={vstr})")
        t0 = time.time()
        try:
            up_signed = client.create_limit_order(token_id=mk["up_tok"], price=up_ask, size=args.size, side="BUY")
            dn_signed = client.create_limit_order(token_id=mk["dn_tok"], price=dn_ask, size=args.size, side="BUY")
            resp = client.post_orders([up_signed, dn_signed])
        except Exception as e:
            log(f"    post error, skipping window: {e}"); time.sleep(2); continue
        trial += 1
        post_ms = (time.time() - t0) * 1000
        up_ok, up_id, up_status, up_fill = classify_post(resp[0])
        dn_ok, dn_id, dn_status, dn_fill = classify_post(resp[1])
        log(f"    posted in {post_ms:.0f}ms | Up:{up_status}(ok={up_ok}) Dn:{dn_status}(ok={dn_ok})")

        # --- poll fills for FILL_WAIT_SEC (catch delayed matches) ---
        deadline = time.time() + args.fill_wait
        while time.time() < deadline:
            time.sleep(POLL_EVERY)
            try:
                if up_id and up_fill < args.size:
                    o = client.get_order(order_id=up_id); up_fill = float(o.size_matched)
                if dn_id and dn_fill < args.size:
                    o = client.get_order(order_id=dn_id); dn_fill = float(o.size_matched)
            except Exception:
                pass
            if up_fill >= args.size and dn_fill >= args.size: break

        up_done = up_fill >= args.size - 1e-6
        dn_done = dn_fill >= args.size - 1e-6
        outcome = ("BOTH" if up_done and dn_done else
                   "NONE" if not up_done and not dn_done else "HALF")
        spent += (up_fill * up_ask + dn_fill * dn_ask)
        log(f"    RESULT={outcome}  up_fill={up_fill:.1f}/{args.size} dn_fill={dn_fill:.1f}/{args.size}")

        # --- emergency handling ---
        action = "none"
        if outcome == "HALF" and not args.no_hedge:
            # cancel the unfilled leg, market-sell the filled leg to flatten
            open_id = up_id if not up_done else dn_id
            filled_tok = mk["up_tok"] if up_done else mk["dn_tok"]
            filled_sz = up_fill if up_done else dn_fill
            try:
                if open_id: client.cancel_order(order_id=open_id)
            except Exception as e:
                log(f"    cancel err: {e}")
            try:
                client.place_market_order(token_id=filled_tok, side="SELL", shares=filled_sz, order_type="FAK")
                action = "canceled_open+sold_filled"
                log(f"    UNWOUND: canceled open leg, market-sold {filled_sz:.1f} shares")
            except Exception as e:
                action = "cancel_ok_sell_failed"
                log(f"    unwind sell err (still holding {filled_sz:.1f}): {e}")
        elif outcome == "NONE":
            for oid in (up_id, dn_id):
                try:
                    if oid: client.cancel_order(order_id=oid)
                except Exception: pass
            action = "canceled_both"
        elif outcome == "BOTH":
            action = "hedged_hold_to_redeem"

        # conservative net-loss estimate (for the spend cap / risk tracking)
        if outcome == "BOTH":
            trial_net = max(0.0, ssum - 1.0) * args.size
        elif outcome == "HALF":
            fsz = up_fill if up_done else dn_fill
            fask = up_ask if up_done else dn_ask
            trial_net = (0.05 * fsz) if action == "canceled_open+sold_filled" else (0.5 * fsz * fask)
        else:
            trial_net = 0.0
        net_loss += trial_net

        rec = {"ts": int(t0), "slug": slug, "ttl": ttl, "up_ask": up_ask, "dn_ask": dn_ask,
               "sum": round(ssum, 4), "size": args.size, "post_ms": round(post_ms),
               "vol_bps": round(vbps, 1) if vbps is not None else None,
               "vol_after": round(vm.vol_bps(), 1) if vm.vol_bps() is not None else None,
               "up_status": up_status, "dn_status": dn_status,
               "up_fill": up_fill, "dn_fill": dn_fill, "outcome": outcome,
               "action": action, "trial_net": round(trial_net, 3),
               "net_loss_cum": round(net_loss, 3), "spent_cum": round(spent, 4)}
        record(rec); results.append(rec)
        log(f"    trial_net~${trial_net:.2f}  net_loss_cum~${net_loss:.2f}  (gross_spent=${spent:.2f})")
        time.sleep(2)

    http.close()
    summarize(results)


def run_dry(args):
    log("DRY RUN — reads live book, prints intended orders, posts NOTHING.")
    http = httpx.Client()
    slug, start, end, ttl = current_btc_window()
    log(f"  current window: {slug}  ttl={ttl}s")
    mk = fetch_market(http, slug)
    if not mk:
        log("  market not found / closed; try again mid-window."); http.close(); return
    up_ask, up_sz = best_ask_rest(http, mk["up_tok"])
    dn_ask, dn_sz = best_ask_rest(http, mk["dn_tok"])
    if up_ask is None or dn_ask is None:
        log("  no asks; skip."); http.close(); return
    ssum = up_ask + dn_ask
    log(f"  up_ask={up_ask:.3f}(x{up_sz:.0f})  dn_ask={dn_ask:.3f}(x{dn_sz:.0f})  sum={ssum:.3f}")
    would_enter = ssum <= args.max_sum and MIN_TTL <= ttl <= MAX_TTL
    log(f"  enter condition (sum<={args.max_sum} & {MIN_TTL}<=ttl<={MAX_TTL}): {would_enter}")
    if would_enter:
        log(f"  WOULD: post_orders([BUY Up @ {up_ask:.3f} x{args.size}, BUY Down @ {dn_ask:.3f} x{args.size}])")
        log(f"  WOULD: est cost ${(up_ask+dn_ask)*args.size:.2f}; on HALF-leg -> cancel open + market-sell filled")
    else:
        log("  WOULD: skip this window (waiting for safe entry).")
    http.close()
    log("DRY RUN complete. To go live: set POLY_PK/POLY_PROXY and drop --dry.")


def summarize(results):
    if not results:
        log("no trials executed."); return
    n = len(results)
    both = sum(1 for r in results if r["outcome"] == "BOTH")
    half = sum(1 for r in results if r["outcome"] == "HALF")
    none = sum(1 for r in results if r["outcome"] == "NONE")
    def avgvol(tag):
        vs = [r["vol_bps"] for r in results if r["outcome"] == tag and r.get("vol_bps") is not None]
        return f"{sum(vs)/len(vs):.1f}bps avg" if vs else "n/a"
    log("=" * 50)
    log(f"SUMMARY: {n} trials | BOTH={both} HALF={half} NONE={none}")
    log(f"  HALF-LEG RATE = {half}/{n} = {100*half/n:.0f}%   (PH was ~100%; target <30%)")
    log(f"  full hedge (both filled) = {100*both/n:.0f}%")
    log(f"  vol@entry: BOTH={avgvol('BOTH')}  HALF={avgvol('HALF')}  NONE={avgvol('NONE')}")
    log(f"  events -> {EVENT_FILE}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="no real orders (no creds needed)")
    ap.add_argument("--trials", type=int, default=MAX_TRIALS)
    ap.add_argument("--size", type=float, default=SIZE_SHARES)
    ap.add_argument("--max-spend", type=float, default=MAX_SPEND_USD)   # gross, logging only
    ap.add_argument("--max-net-loss", type=float, default=6.0, help="stop once est. net loss hits this")
    ap.add_argument("--max-sum", type=float, default=MAX_ENTER_SUM)
    ap.add_argument("--fill-wait", type=float, default=FILL_WAIT_SEC)
    ap.add_argument("--min-vol-bps", type=float, default=0.0,
                    help="only enter when BTC 20s volatility >= this many bps (hard-case test)")
    ap.add_argument("--no-hedge", action="store_true", help="don't auto-unwind half-legs (riskier)")
    args = ap.parse_args()
    args.trials = min(args.trials, 30)              # absolute cap
    args.max_net_loss = min(args.max_net_loss, 15.0)  # absolute net-loss cap
    args.max_spend = min(args.max_spend, 80.0)

    pk, proxy = load_env()
    if args.dry:
        run_dry(args); return
    if not pk or not proxy:
        log("REAL mode needs POLY_PK and POLY_PROXY env vars (or .env). Aborting.")
        log("  Run with --dry to validate logic without credentials/orders.")
        sys.exit(1)
    log(f"REAL MONEY MODE | asset={ASSET} trials={args.trials} size={args.size} "
        f"max_net_loss=${args.max_net_loss} max_enter_sum={args.max_sum} vol_gate={args.min_vol_bps}bps")
    run_real(pk, proxy, args)


if __name__ == "__main__":
    main()
