#!/usr/bin/env python3
"""
LIVE Momentum Sniper — Real Polymarket Trading
================================================
Uses STRONG signals (conf>=75%) to place real orders on BTC Up/Down markets.

Usage:
    python sniper_live.py              # Default: $1 per trade, 60s sample
    python sniper_live.py 2.0          # $2 per trade
    python sniper_live.py 2.0 50       # $2/trade, 50 cycles
"""
import asyncio
import sys
import os
import json
import time
import httpx
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies import MomentumSniper, Signal
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import (
    ApiCreds, OrderArgs, PartialCreateOrderOptions,
    BalanceAllowanceParams, AssetType
)
from py_clob_client.order_builder.constants import BUY


# ─── Config ───────────────────────────────────────────────────
import os
PK = os.environ.get("POLY_PK") or ""
PROXY = os.environ.get("POLY_PROXY") or ""
if not PK or not PROXY:
    raise RuntimeError(
        "Set POLY_PK and POLY_PROXY env vars before running.\n"
        "Linux/Mac: export POLY_PK=0x... ; export POLY_PROXY=0x...\n"
        "Windows:   $env:POLY_PK='0x...' ; $env:POLY_PROXY='0x...'\n"
        "Or copy .env.example to .env and source it."
    )
CHAIN_ID = 137
SIG_TYPE = 2

COLLECT_SECONDS = 60
WAIT_SECONDS = 180
MIN_CONFIDENCE = 0.75
TICK_SIZE = "0.01"


# ─── Polymarket Client ───────────────────────────────────────
def create_clob_client() -> ClobClient:
    client = ClobClient(
        "https://clob.polymarket.com",
        key=PK,
        chain_id=CHAIN_ID,
        signature_type=SIG_TYPE,
        funder=PROXY,
    )
    creds = client.create_or_derive_api_creds()
    client.set_api_creds(creds)
    return client


def get_usdc_balance(client: ClobClient) -> float:
    params = BalanceAllowanceParams(
        asset_type=AssetType.COLLATERAL, signature_type=SIG_TYPE
    )
    bal = client.get_balance_allowance(params)
    return int(bal["balance"]) / 1e6


# ─── Market Discovery ────────────────────────────────────────
async def find_btc_updown_market(http: httpx.AsyncClient) -> Optional[dict]:
    """Find the nearest open BTC Up/Down hourly market."""
    now = datetime.now()
    # Try current and next hours
    from datetime import timedelta

    candidates = []
    for delta_h in range(0, 6):
        t = now + timedelta(hours=delta_h)
        # Polymarket uses ET (UTC-4 in EDT)
        # Construct slug patterns
        month = t.strftime("%B").lower()  # april
        day = t.day
        year = t.year

        for hour in range(0, 24):
            ampm = "am" if hour < 12 else "pm"
            h12 = hour % 12 or 12
            slug = f"bitcoin-up-or-down-{month}-{day}-{year}-{h12}{ampm}-et"
            candidates.append(slug)

    # Also try sub-hour markets (15min, 5min)
    # But start with hourly as they have more liquidity

    # Batch check — just try a few likely ones
    for slug in candidates[:12]:
        try:
            r = await http.get(
                f"https://gamma-api.polymarket.com/events?slug={slug}",
                timeout=10,
            )
            if r.status_code == 200 and r.json():
                data = r.json()
                ev = data[0] if isinstance(data, list) else data
                markets = ev.get("markets", [])
                for m in markets:
                    if m.get("closed"):
                        continue
                    outcomes = json.loads(m["outcomes"]) if isinstance(m["outcomes"], str) else m["outcomes"]
                    tokens = json.loads(m["clobTokenIds"]) if isinstance(m["clobTokenIds"], str) else m["clobTokenIds"]
                    if "Up" in outcomes and "Down" in outcomes:
                        up_idx = outcomes.index("Up")
                        down_idx = outcomes.index("Down")
                        prices = json.loads(m["outcomePrices"]) if isinstance(m["outcomePrices"], str) else m["outcomePrices"]
                        return {
                            "question": m.get("question", ""),
                            "slug": slug,
                            "up_token": tokens[up_idx],
                            "down_token": tokens[down_idx],
                            "up_price": float(prices[up_idx]),
                            "down_price": float(prices[down_idx]),
                            "neg_risk": m.get("negRisk", False),
                            "condition_id": m.get("conditionId", ""),
                        }
        except Exception:
            continue
    return None


async def find_nearest_market(http: httpx.AsyncClient) -> Optional[dict]:
    """Find any open BTC Up/Down market by searching multiple time slots."""
    now = datetime.now()

    # Try a broader search using event listing
    try:
        # Search recent events
        for page in range(3):
            r = await http.get(
                "https://gamma-api.polymarket.com/events",
                params={
                    "limit": 50,
                    "offset": page * 50,
                    "closed": "false",
                    "order": "startDate",
                    "ascending": "false",
                },
                timeout=15,
            )
            if r.status_code != 200:
                continue
            events = r.json()
            for ev in events:
                title = ev.get("title", "")
                if "bitcoin" in title.lower() and "up or down" in title.lower():
                    for m in ev.get("markets", []):
                        if m.get("closed"):
                            continue
                        outcomes = json.loads(m["outcomes"]) if isinstance(m["outcomes"], str) else m["outcomes"]
                        tokens = json.loads(m["clobTokenIds"]) if isinstance(m["clobTokenIds"], str) else m["clobTokenIds"]
                        if "Up" in outcomes and "Down" in outcomes:
                            up_idx = outcomes.index("Up")
                            down_idx = outcomes.index("Down")
                            prices = json.loads(m["outcomePrices"]) if isinstance(m["outcomePrices"], str) else m["outcomePrices"]
                            neg_risk_resp = await http.get(
                                "https://clob.polymarket.com/neg-risk",
                                params={"token_id": tokens[up_idx]},
                                timeout=10,
                            )
                            neg_risk = False
                            if neg_risk_resp.status_code == 200:
                                neg_risk = neg_risk_resp.json().get("neg_risk", False)
                            return {
                                "question": m.get("question", ""),
                                "slug": ev.get("slug", ""),
                                "up_token": tokens[up_idx],
                                "down_token": tokens[down_idx],
                                "up_price": float(prices[up_idx]),
                                "down_price": float(prices[down_idx]),
                                "neg_risk": neg_risk,
                                "condition_id": m.get("conditionId", ""),
                            }
    except Exception as e:
        print(f"[WARN] Market search error: {e}")

    # Fallback: try specific slugs
    return await find_btc_updown_market(http)


# ─── Order Placement ─────────────────────────────────────────
def place_order(
    client: ClobClient,
    token_id: str,
    price: float,
    size_usd: float,
    neg_risk: bool,
) -> Optional[dict]:
    """Place a real order. size_usd = dollar amount to spend."""
    # shares = usd / price
    shares = round(size_usd / price, 2)
    if shares < 5:
        shares = 5.0

    # Clamp price to valid range
    price = max(0.01, min(0.99, round(price, 2)))

    order_args = OrderArgs(
        token_id=token_id,
        price=price,
        size=shares,
        side=BUY,
    )
    options = PartialCreateOrderOptions(tick_size=TICK_SIZE, neg_risk=neg_risk)

    try:
        result = client.create_and_post_order(order_args, options)
        return result
    except Exception as e:
        print(f"[ORDER ERROR] {e}")
        return None


# ─── Main Loop ───────────────────────────────────────────────
@dataclass
class LiveStats:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    skipped: int = 0
    total_spent: float = 0.0
    orders: list = field(default_factory=list)


async def run_live_sniper(
    trade_size: float = 1.0,
    max_cycles: int = 0,
):
    sniper = MomentumSniper(balance=0, max_bet_pct=1.0)  # balance tracked via USDC
    client = create_clob_client()
    http = httpx.AsyncClient(timeout=30.0)
    stats = LiveStats()

    # Get initial balance
    balance = get_usdc_balance(client)

    print(f"""
{'='*60}
  MOMENTUM SNIPER — LIVE TRADING
{'='*60}
  Wallet:      {PROXY[:12]}...
  USDC Balance: ${balance:.2f}
  Trade Size:  ${trade_size:.2f} per signal
  Sampling:    {COLLECT_SECONDS}s
  Wait:        {WAIT_SECONDS}s
  Filter:      STRONG only, conf >= {MIN_CONFIDENCE:.0%}
  Cycles:      {'infinite' if max_cycles == 0 else max_cycles}
{'='*60}
  Press Ctrl+C to stop
{'='*60}
""")

    if balance < trade_size * 2:
        print(f"[ERROR] Insufficient balance (${balance:.2f}). Need at least ${trade_size*2:.2f}")
        await http.aclose()
        return

    cycle = 0
    try:
        while max_cycles == 0 or cycle < max_cycles:
            cycle += 1
            print(f"\n{'='*60}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Cycle #{cycle}")
            print(f"{'='*60}")

            # 1. Find active BTC Up/Down market
            market = await find_nearest_market(http)
            if not market:
                print("[WARN] No active BTC Up/Down market found. Retrying in 60s...")
                await asyncio.sleep(60)
                continue

            print(f"[MARKET] {market['question']}")
            print(f"  Up: ${market['up_price']:.3f} | Down: ${market['down_price']:.3f}")

            # 2. Collect ticks & analyze
            open_price = await sniper.fetcher.fetch_price()
            if open_price is None:
                print("[ERROR] Cannot fetch BTC price. Retrying in 10s...")
                await asyncio.sleep(10)
                continue
            print(f"[BTC] ${open_price:,.2f}")

            signal = await sniper.analyze_momentum(
                collect_seconds=COLLECT_SECONDS,
                tick_interval=2.0,
            )
            print(sniper.format_signal(signal))

            # 3. Check if tradeable (STRONG + conf >= 75%)
            tradeable = (
                signal.signal in (Signal.STRONG_UP, Signal.STRONG_DOWN)
                and signal.confidence >= MIN_CONFIDENCE
            )

            if not tradeable:
                stats.skipped += 1
                print(f"[SKIP] {signal.signal.value} conf:{signal.confidence:.0%}")
                print(f"[WAIT] {WAIT_SECONDS}s until next cycle...")
                await asyncio.sleep(WAIT_SECONDS)
                continue

            # 4. Determine direction and tokens
            if signal.direction == "Up":
                main_token = market["up_token"]
                hedge_token = market["down_token"]
                main_price = market["up_price"]
                hedge_price = market["down_price"]
            else:
                main_token = market["down_token"]
                hedge_token = market["up_token"]
                main_price = market["down_price"]
                hedge_price = market["up_price"]

            # Position sizing: 90/10 hedge
            main_usd = trade_size * 0.90
            hedge_usd = trade_size * 0.10

            print(f"\n[TRADE] Predicted: {signal.direction} (conf: {signal.confidence:.0%})")
            print(f"  Main:  ${main_usd:.2f} on {signal.direction} @ ${main_price:.3f}")
            print(f"  Hedge: ${hedge_usd:.2f} on {signal.opposite_direction} @ ${hedge_price:.3f}")

            # 5. Place orders
            print(f"[ORDER] Placing main order...")
            main_result = place_order(
                client, main_token, main_price, main_usd, market["neg_risk"]
            )

            if main_result and main_result.get("success"):
                print(f"  MAIN: {main_result['status']} | ID: {main_result['orderID'][:16]}...")
                order_record = {
                    "cycle": cycle,
                    "time": datetime.now().isoformat(),
                    "direction": signal.direction,
                    "signal": signal.signal.value,
                    "confidence": signal.confidence,
                    "main_order": main_result,
                    "main_usd": main_usd,
                    "market": market["question"],
                    "btc_open": open_price,
                }

                # Place hedge
                print(f"[ORDER] Placing hedge order...")
                hedge_result = place_order(
                    client, hedge_token, hedge_price, hedge_usd, market["neg_risk"]
                )
                if hedge_result and hedge_result.get("success"):
                    print(f"  HEDGE: {hedge_result['status']} | ID: {hedge_result['orderID'][:16]}...")
                    order_record["hedge_order"] = hedge_result
                    order_record["hedge_usd"] = hedge_usd
                else:
                    print(f"  HEDGE: Failed (main still active)")
                    order_record["hedge_order"] = None

                stats.orders.append(order_record)
                stats.trades += 1
                stats.total_spent += main_usd + (hedge_usd if hedge_result else 0)
            else:
                print(f"  MAIN: FAILED — {main_result}")

            # 6. Wait for resolution
            print(f"\n[WAIT] {WAIT_SECONDS}s for market resolution...")
            await asyncio.sleep(WAIT_SECONDS)

            # 7. Check result
            close_price = await sniper.fetcher.fetch_price()
            if close_price:
                actual = "Up" if close_price > open_price else "Down"
                change_pct = (close_price - open_price) / open_price * 100
                won = signal.direction == actual

                if won:
                    stats.wins += 1
                    estimated_pnl = main_usd - hedge_usd
                else:
                    stats.losses += 1
                    estimated_pnl = hedge_usd - main_usd

                icon = "WIN" if won else "LOSS"
                print(f"\n{'='*50}")
                print(f"  RESULT: {'*' if won else 'x'} {icon}")
                print(f"  BTC: ${open_price:,.2f} -> ${close_price:,.2f} ({change_pct:+.4f}%)")
                print(f"  Predicted: {signal.direction} | Actual: {actual}")
                print(f"  Est P&L: ${estimated_pnl:+.2f}")
                print(f"{'='*50}")

                if stats.orders:
                    stats.orders[-1]["btc_close"] = close_price
                    stats.orders[-1]["actual"] = actual
                    stats.orders[-1]["won"] = won
                    stats.orders[-1]["est_pnl"] = estimated_pnl

            # 8. Updated balance
            try:
                balance = get_usdc_balance(client)
                print(f"[BALANCE] ${balance:.2f}")
            except:
                pass

            # 9. Running stats
            if stats.trades > 0:
                wr = 100 * stats.wins / stats.trades
                print(f"\n[STATS] {stats.trades} trades | "
                      f"W:{stats.wins} L:{stats.losses} Skip:{stats.skipped} | "
                      f"WR: {wr:.0f}% | Spent: ${stats.total_spent:.2f}")

    except KeyboardInterrupt:
        print("\n\n[STOP] Stopped by user")
    finally:
        await sniper.close()
        await http.aclose()

        # Save log
        log_dir = os.path.join(os.environ.get("TEMP", "."), "polymarket_trader")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "live_sniper_log.json")
        try:
            with open(log_file, "w") as f:
                json.dump({
                    "trades": stats.trades,
                    "wins": stats.wins,
                    "losses": stats.losses,
                    "skipped": stats.skipped,
                    "total_spent": stats.total_spent,
                    "orders": stats.orders,
                }, f, indent=2, default=str)
            print(f"[LOG] Saved to {log_file}")
        except Exception as e:
            print(f"[WARN] Could not save log: {e}")

        # Final balance
        try:
            balance = get_usdc_balance(client)
        except:
            pass

        print(f"""
{'='*60}
  FINAL — {stats.trades} trades | W:{stats.wins} L:{stats.losses}
  WR: {100*stats.wins/stats.trades:.0f}% | Spent: ${stats.total_spent:.2f}
  Balance: ${balance:.2f}
{'='*60}
""" if stats.trades > 0 else f"\n[DONE] No trades placed. Balance: ${balance:.2f}")


if __name__ == "__main__":
    trade_size = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    max_cycles = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    asyncio.run(run_live_sniper(trade_size=trade_size, max_cycles=max_cycles))
