"""Backtest CHOP threshold variations on current Option B + C2 setup."""
import json, sys, time, statistics
from collections import defaultdict
from datetime import datetime, timezone

import httpx

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError): pass


def fetch_btc_candles(days=10):
    candles = []
    end_ms = int(time.time() * 1000)
    target = end_ms - days * 86400 * 1000
    with httpx.Client() as c:
        while end_ms > target:
            r = c.get("https://api.binance.com/api/v3/klines",
                      params={"symbol": "BTCUSDT", "interval": "5m",
                              "endTime": end_ms, "limit": 1000}, timeout=15)
            if r.status_code != 200: break
            batch = r.json()
            if not batch: break
            candles = batch + candles
            oldest = batch[0][0]
            if oldest <= target: break
            end_ms = oldest - 1
            if len(candles) > 5000: break
    return candles


def vel_at(candles, target_ts, lookback):
    target_ms = target_ts * 1000
    idx = None
    for i, c in enumerate(candles):
        if c[0] <= target_ms < c[6]:
            idx = i; break
        if c[0] > target_ms:
            idx = i - 1 if i > 0 else None
            break
    if idx is None or idx < lookback: return None
    cur = float(candles[idx][4]); old = float(candles[idx - lookback][4])
    return (cur - old) / old * 100 if old > 0 else None


def load_eebde():
    by_market = defaultdict(list)
    with open(r".\eebde_history.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            try: ev = json.loads(line)
            except: continue
            if ev.get("type") != "TRADE" or ev.get("side") != "BUY": continue
            by_market[ev["conditionId"]].append(ev)
    winners = {}
    for cid, evs in by_market.items():
        evs.sort(key=lambda e: e.get("timestamp", 0))
        last_px = {}
        for ev in evs:
            oc, px = ev.get("outcome"), ev.get("price")
            if oc and px is not None: last_px[oc] = px
        w = None
        for oc, px in last_px.items():
            if px >= 0.9: w = oc; break
        if w: winners[cid] = w
    return by_market, winners


print("=== Loading data ===")
candles = fetch_btc_candles(10)
print(f"  BTC candles: {len(candles)}")
by_market, winners = load_eebde()
print(f"  eebde markets: {len(by_market)} ({len(winners)} resolved)")

# Get drift proxy (top_ask at our entry time = next same-outcome trade ~30s later)
all_trades_by_market = defaultdict(list)
for cid, evs in by_market.items():
    for e in evs:
        all_trades_by_market[cid].append((e["timestamp"], e.get("price",0), e.get("outcome")))
    all_trades_by_market[cid].sort()

def get_top_ask_proxy(cid, outcome, after_ts):
    for ts, px, oc in all_trades_by_market[cid]:
        if ts < after_ts + 20: continue  # need 20s+ lag
        if ts > after_ts + 90: break
        if oc == outcome:
            return px
    return None


def slug_settle(slug):
    if "btc-updown-15m-" in slug:
        try: return int(slug.rsplit("-",1)[1]) + 15*60
        except: return None
    if "btc-updown-5m-" in slug:
        try: return int(slug.rsplit("-",1)[1]) + 5*60
        except: return None
    return None


# Build candidate set with all features
print("\n=== Building candidates with features (Option B + C2 base) ===")
candidates = []
for cid, evs in by_market.items():
    if cid not in winners: continue
    slug = evs[0].get("slug", "")
    if not ("btc-updown-5m-" in slug or "btc-updown-15m-" in slug): continue
    settle = slug_settle(slug)
    if not settle: continue
    for ev in evs:
        px = ev.get("price", 0)
        sz = ev.get("usdcSize", 0)
        # Option B filter
        if not (0.60 <= px <= 0.80): continue
        if sz < 30: continue
        ts = ev["timestamp"]
        # Drift proxy
        proxy = get_top_ask_proxy(cid, ev["outcome"], ts)
        if proxy is None:
            entry_real = px + 0.01
            drift_c = 0
        else:
            entry_real = proxy + 0.01
            drift_c = (proxy - px) * 100
        # Apply other filters
        if entry_real < 0.75: continue  # C2 filter
        if drift_c < -5: continue  # negative drift filter
        if drift_c > 4: continue  # max drift filter
        # vel5 at time
        v5 = vel_at(candles, ts, 5)
        if v5 is None: continue
        candidates.append({
            "cid": cid, "ts": ts, "outcome": ev["outcome"],
            "winner": winners[cid],
            "entry": entry_real, "drift": drift_c,
            "vel5": v5, "leader_price": px, "leader_size": sz,
        })

print(f"  {len(candidates)} candidates passed all filters except chop")


def sim_pnl(c, target=2.0):
    if c["entry"] >= 1: return 0, 0, False
    shares = max(5.0, target / c["entry"])
    cost = shares * c["entry"]
    won = c["outcome"] == c["winner"]
    pnl = (shares - cost) if won else -cost
    return pnl, cost, won


print("\n=== Chop threshold sweep ===\n")
print(f"{'CHOP threshold':<20} {'n_kept':<8} {'n_skipped':<10} {'WR':<7} {'PnL':<8} {'ROI':<7}")

for thresh in [0.00, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.70, 1.00]:
    kept = [c for c in candidates if abs(c["vel5"]) >= thresh]
    if not kept:
        print(f"  >= {thresh:.2f}%             0          {len(candidates)}        n/a")
        continue
    total_pnl = 0; total_cost = 0; wins = 0
    for c in kept:
        pnl, cost, won = sim_pnl(c)
        total_pnl += pnl; total_cost += cost
        if won: wins += 1
    n = len(kept)
    wr = wins/n*100
    roi = total_pnl/total_cost*100 if total_cost > 0 else 0
    skipped = len(candidates) - n
    print(f"  >= {thresh:.2f}%             {n:<8} {skipped:<10} {wr:<5.1f}% ${total_pnl:<+6.0f} {roi:+5.2f}%")


# Now compare with current strategy (chop 0.20 baseline)
print("\n=== Detailed: chop 0.20 vs 0.35 head-to-head ===")
for thresh in [0.20, 0.35]:
    kept = [c for c in candidates if abs(c["vel5"]) >= thresh]
    daily_pnl = defaultdict(float)
    for c in kept:
        d = datetime.fromtimestamp(c["ts"], tz=timezone.utc).strftime("%Y-%m-%d")
        pnl, _, _ = sim_pnl(c)
        daily_pnl[d] += pnl
    total = sum(daily_pnl.values())
    n_days = len(daily_pnl)
    avg_daily = total/max(n_days,1)
    pos_days = sum(1 for v in daily_pnl.values() if v > 0)
    neg_days = sum(1 for v in daily_pnl.values() if v < 0)
    print(f"\n  chop {thresh:.2f}%:")
    print(f"    n trades: {len(kept)}")
    print(f"    PnL: ${total:+.0f}")
    print(f"    days: {n_days} (pos={pos_days} neg={neg_days})")
    print(f"    avg/day: ${avg_daily:+.2f}")
    print(f"    daily distribution:")
    for d in sorted(daily_pnl.keys()):
        print(f"      {d}: ${daily_pnl[d]:+.2f}")


# Also test vel15 instead of vel5
print("\n=== Try vel15 instead of vel5 ===\n")
print("(annotating candidates with vel15)")
for c in candidates:
    c["vel15"] = vel_at(candles, c["ts"], 15)
canv = [c for c in candidates if c.get("vel15") is not None]
print(f"  candidates with vel15: {len(canv)}\n")
print(f"{'vel15 threshold':<20} {'n_kept':<8} {'WR':<7} {'PnL':<8} {'ROI':<7}")
for thresh in [0.00, 0.20, 0.30, 0.40, 0.50, 0.70, 1.00, 1.50]:
    kept = [c for c in canv if abs(c["vel15"]) >= thresh]
    if not kept: continue
    total_pnl = 0; total_cost = 0; wins = 0
    for c in kept:
        pnl, cost, won = sim_pnl(c)
        total_pnl += pnl; total_cost += cost
        if won: wins += 1
    n = len(kept); wr = wins/n*100
    roi = total_pnl/total_cost*100 if total_cost > 0 else 0
    print(f"  >= {thresh:.2f}%             {n:<8} {wr:<5.1f}% ${total_pnl:<+6.0f} {roi:+5.2f}%")

# Combined: both vel5 AND vel15 must exceed thresholds
print("\n=== Combined vel5 + vel15 thresholds ===\n")
print(f"{'config':<35} {'n':<6} {'WR':<7} {'ROI':<7}")
for v5_thr, v15_thr in [(0.20, 0.30), (0.20, 0.50), (0.30, 0.40), (0.30, 0.50), (0.35, 0.30), (0.35, 0.50)]:
    kept = [c for c in canv if abs(c["vel5"]) >= v5_thr and abs(c["vel15"]) >= v15_thr]
    if not kept: continue
    total_pnl = 0; total_cost = 0; wins = 0
    for c in kept:
        pnl, cost, won = sim_pnl(c)
        total_pnl += pnl; total_cost += cost
        if won: wins += 1
    n = len(kept); roi = total_pnl/total_cost*100 if total_cost > 0 else 0
    print(f"  vel5>={v5_thr}, vel15>={v15_thr}:        {n:<6} {wins/n*100:<5.1f}% {roi:+5.2f}%")
