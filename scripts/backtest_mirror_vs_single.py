"""Backtest: mirror (both sides) vs single-side eebde follow.

For each resolved BTC market eebde traded:
  - Single: copy FIRST BUY only (current sim behavior)
  - Mirror: copy FIRST Up BUY + FIRST Down BUY
  - Compute PnL with 1c slippage proxy

Min 5 shares per leg (real Polymarket constraint).
"""
import json, sys, time
from collections import defaultdict
from datetime import datetime, timezone

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError): pass

CUTOFF = int(time.time()) - 7 * 86400
MIN_SHARES = 5.0
SLIP_C = 0.01  # +1c slippage per leg
TARGET_USDC = 2.0

print("=== Loading eebde history ===")
by_market = defaultdict(list)
with open(r".\eebde_history.jsonl") as f:
    for line in f:
        try: ev = json.loads(line)
        except: continue
        if ev.get("type") != "TRADE" or ev.get("side") != "BUY": continue
        slug = ev.get("slug") or ""
        if not ("btc-updown-5m-" in slug or "btc-updown-15m-" in slug): continue
        if ev.get("timestamp", 0) < CUTOFF: continue
        by_market[ev["conditionId"]].append(ev)

print(f"  eebde BTC markets in last 7d: {len(by_market)}")

# Determine winner via last-price > 0.9 heuristic
winners = {}
for cid, evs in by_market.items():
    evs.sort(key=lambda e: e["timestamp"])
    last_px = {}
    for ev in evs:
        last_px[ev["outcome"]] = ev["price"]
    for oc, px in last_px.items():
        if px >= 0.9: winners[cid] = oc; break
print(f"  resolved: {len(winners)}")

# Top-ask proxy: price of next same-outcome trade ~30s later
all_trades = defaultdict(list)
for cid, evs in by_market.items():
    for e in evs:
        all_trades[cid].append((e["timestamp"], e.get("price",0), e.get("outcome")))
    all_trades[cid].sort()

def get_proxy(cid, outcome, after_ts):
    for ts, px, oc in all_trades[cid]:
        if ts < after_ts + 20: continue
        if ts > after_ts + 90: break
        if oc == outcome: return px
    return None


def sim_leg(leader_px, outcome_chosen, winner):
    """Simulate one leg buy with slippage. Returns (cost, payout, pnl, won)."""
    proxy = leader_px
    entry = round(min(0.99, proxy + SLIP_C), 4)
    if entry >= 1.0: return None
    shares = max(MIN_SHARES, TARGET_USDC / entry)
    cost = shares * entry
    won = (outcome_chosen == winner)
    payout = shares * 1.0 if won else 0.0
    return cost, payout, payout - cost, won


# Single-side strategy
print("\n=== Strategy 1: SINGLE-SIDE (current sim) ===")
single_pnl = 0; single_cost = 0; single_wins = 0; single_trades = 0
daily_single = defaultdict(float)
for cid, evs in by_market.items():
    if cid not in winners: continue
    first_buy = evs[0]
    # Use top_ask proxy for entry
    proxy = get_proxy(cid, first_buy["outcome"], first_buy["timestamp"]) or first_buy["price"]
    r = sim_leg(proxy, first_buy["outcome"], winners[cid])
    if r is None: continue
    cost, payout, pnl, won = r
    single_pnl += pnl; single_cost += cost; single_trades += 1
    if won: single_wins += 1
    d = datetime.fromtimestamp(first_buy["timestamp"], tz=timezone.utc).strftime("%Y-%m-%d")
    daily_single[d] += pnl

print(f"  trades: {single_trades}, wins: {single_wins} ({single_wins/single_trades*100:.1f}%)")
print(f"  total cost: ${single_cost:.0f}")
print(f"  PnL: ${single_pnl:+.0f}")
print(f"  ROI: {single_pnl/single_cost*100:+.2f}%")


# Mirror strategy
print("\n=== Strategy 2: MIRROR (copy both sides if seen) ===")
mirror_pnl = 0; mirror_cost = 0
n_pairs_complete = 0; n_pairs_partial = 0
guaranteed_profit_pairs = 0; guaranteed_loss_pairs = 0
daily_mirror = defaultdict(float)
for cid, evs in by_market.items():
    if cid not in winners: continue
    # Find first Up BUY and first Down BUY
    first_up = next((e for e in evs if e["outcome"] == "Up"), None)
    first_dn = next((e for e in evs if e["outcome"] == "Down"), None)

    legs = []
    if first_up:
        proxy = get_proxy(cid, "Up", first_up["timestamp"]) or first_up["price"]
        r = sim_leg(proxy, "Up", winners[cid])
        if r: legs.append(("Up", first_up["timestamp"], proxy, r))
    if first_dn:
        proxy = get_proxy(cid, "Down", first_dn["timestamp"]) or first_dn["price"]
        r = sim_leg(proxy, "Down", winners[cid])
        if r: legs.append(("Down", first_dn["timestamp"], proxy, r))

    if not legs: continue

    if len(legs) == 2:
        n_pairs_complete += 1
        total_cost = sum(l[3][0] for l in legs)
        total_payout = sum(l[3][1] for l in legs)  # one leg wins
        pnl = total_payout - total_cost
        if pnl > 0: guaranteed_profit_pairs += 1
        else: guaranteed_loss_pairs += 1
        mirror_pnl += pnl
        mirror_cost += total_cost
        d = datetime.fromtimestamp(legs[0][1], tz=timezone.utc).strftime("%Y-%m-%d")
        daily_mirror[d] += pnl
    else:
        n_pairs_partial += 1
        cost, payout, pnl, won = legs[0][3]
        mirror_pnl += pnl
        mirror_cost += cost
        d = datetime.fromtimestamp(legs[0][1], tz=timezone.utc).strftime("%Y-%m-%d")
        daily_mirror[d] += pnl

print(f"  complete pairs: {n_pairs_complete}")
print(f"  partial (only one side): {n_pairs_partial}")
print(f"  pairs guaranteed profit: {guaranteed_profit_pairs}")
print(f"  pairs guaranteed loss: {guaranteed_loss_pairs}")
print(f"  total cost: ${mirror_cost:.0f}")
print(f"  PnL: ${mirror_pnl:+.0f}")
print(f"  ROI: {mirror_pnl/mirror_cost*100:+.2f}%")


# Daily comparison
print("\n=== Daily comparison ===")
all_days = sorted(set(daily_single.keys()) | set(daily_mirror.keys()))
print(f"{'date':<12} {'single':>10} {'mirror':>10}")
for d in all_days:
    s = daily_single.get(d, 0); m = daily_mirror.get(d, 0)
    print(f"  {d}  ${s:>+8.2f}  ${m:>+8.2f}")


# Per-pair distribution (mirror)
print("\n=== Mirror pair-by-pair distribution ===")
pair_pnls = []
for cid, evs in by_market.items():
    if cid not in winners: continue
    first_up = next((e for e in evs if e["outcome"] == "Up"), None)
    first_dn = next((e for e in evs if e["outcome"] == "Down"), None)
    if not (first_up and first_dn): continue
    proxy_u = get_proxy(cid, "Up", first_up["timestamp"]) or first_up["price"]
    proxy_d = get_proxy(cid, "Down", first_dn["timestamp"]) or first_dn["price"]
    ru = sim_leg(proxy_u, "Up", winners[cid]); rd = sim_leg(proxy_d, "Down", winners[cid])
    if not (ru and rd): continue
    total_cost = ru[0] + rd[0]
    payout = max(ru[1], rd[1])
    pnl = payout - total_cost
    sum_entry = (proxy_u + SLIP_C) + (proxy_d + SLIP_C)
    pair_pnls.append((sum_entry, pnl))

if pair_pnls:
    pair_pnls.sort(key=lambda x: x[0])
    n = len(pair_pnls)
    buckets = {"<0.95": [], "0.95-1.00": [], "1.00-1.05": [], "1.05-1.10": [], ">1.10": []}
    for sum_e, pnl in pair_pnls:
        if sum_e < 0.95: buckets["<0.95"].append(pnl)
        elif sum_e < 1.00: buckets["0.95-1.00"].append(pnl)
        elif sum_e < 1.05: buckets["1.00-1.05"].append(pnl)
        elif sum_e < 1.10: buckets["1.05-1.10"].append(pnl)
        else: buckets[">1.10"].append(pnl)
    print(f"  {'sum(entry)':<12} {'n':>6} {'avgPnL':>10} {'totalPnL':>10}")
    for k, vs in buckets.items():
        if not vs: continue
        avg = sum(vs)/len(vs); tot = sum(vs)
        print(f"  {k:<12} {len(vs):>6} ${avg:>+8.2f} ${tot:>+8.2f}")


print(f"\n\n*** SUMMARY ***")
print(f"  SINGLE-side ROI: {single_pnl/single_cost*100:+.2f}% (${single_pnl:+.0f} / 7d / {single_trades} trades)")
print(f"  MIRROR ROI:      {mirror_pnl/mirror_cost*100:+.2f}% (${mirror_pnl:+.0f} / 7d / {n_pairs_complete} pairs)")
print(f"  Avg per pair (mirror): ${mirror_pnl/max(n_pairs_complete,1):+.3f}")
