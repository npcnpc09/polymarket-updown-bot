"""Polymarket latency + environment baseline test."""
import asyncio, json, socket, statistics, time, sys, platform
from datetime import datetime, timezone
import httpx

ENDPOINTS = {
    "clob_market": "https://clob.polymarket.com/markets/0xe11788f9e2fa72e93f01b27ed2b94a4dea1b8a8f0f1c45b39e5b3b3e84b9a0f9",
    "data_api":    "https://data-api.polymarket.com/activity?user=0xeebde7a0e019a63e6b476eb425505b7b3e6eba30&limit=1",
    "gamma":       "https://gamma-api.polymarket.com/events?slug=btc-updown-5m-1780063200",
    "book":        "https://clob.polymarket.com/book?token_id=86477388912240063425968488533648571842432556728263832735069050797247776619810",
}

def banner(s): print(f"\n{'='*50}\n  {s}\n{'='*50}")

def env_info():
    banner("ENVIRONMENT")
    print(f"  python: {sys.version.split()[0]}")
    print(f"  platform: {platform.system()} {platform.release()}")

def public_ip_geo():
    banner("LOCATION")
    try:
        r = httpx.get("https://ipinfo.io/json", timeout=5).json()
        print(f"  ip: {r.get('ip')}")
        print(f"  city: {r.get('city')}, {r.get('region')}, {r.get('country')}")
        print(f"  org: {r.get('org')}")
    except Exception as e: print(f"  err: {e}")

def dns_resolve():
    banner("DNS")
    for host in ["clob.polymarket.com", "data-api.polymarket.com",
                 "gamma-api.polymarket.com", "ws-subscriptions-clob.polymarket.com"]:
        try:
            t0 = time.perf_counter()
            ips = socket.gethostbyname_ex(host)[2]
            ms = (time.perf_counter() - t0) * 1000
            print(f"  {host:<45} {ms:>6.1f}ms → {ips[:2]}")
        except Exception as e: print(f"  {host:<45} ERR: {e}")

def http_latency(samples=20):
    banner(f"HTTP LATENCY ({samples} samples each)")
    for name, url in ENDPOINTS.items():
        lats = []
        with httpx.Client(timeout=10) as c:
            try: c.get(url)
            except: pass
            for _ in range(samples):
                t0 = time.perf_counter()
                try:
                    r = c.get(url)
                    if r.status_code in (200, 404):
                        lats.append((time.perf_counter() - t0) * 1000)
                except: pass
        if lats:
            qs = statistics.quantiles(lats, n=10)
            print(f"  {name:<14} n={len(lats)} min={min(lats):>5.1f} p10={qs[0]:>5.1f} med={statistics.median(lats):>5.1f} p90={qs[8]:>5.1f} max={max(lats):>5.1f} ms")

def parallel_book():
    banner("PARALLEL 20 ORDERBOOK FETCH")
    from concurrent.futures import ThreadPoolExecutor
    with httpx.Client(timeout=10) as c:
        now = int(time.time())
        s5 = now // 300 * 300; s15 = now // 900 * 900
        tokens = []
        for asset in ["btc","eth","sol","xrp"]:
            for slot, kind in [(s5,"5m"),(s5+300,"5m"),(s15,"15m"),(s15+900,"15m")]:
                slug = f"{asset}-updown-{kind}-{slot}"
                try:
                    r = c.get("https://gamma-api.polymarket.com/events", params={"slug": slug}, timeout=5)
                    if r.status_code != 200: continue
                    for ev in r.json():
                        for m in ev.get("markets", []):
                            tids = m.get("clobTokenIds")
                            if isinstance(tids, str): tids = json.loads(tids)
                            if tids: tokens.extend(str(t) for t in tids[:2])
                except: continue
                if len(tokens) >= 40: break
            if len(tokens) >= 40: break
        tokens = tokens[:40]
        print(f"  collected {len(tokens)} token_ids")
        if not tokens: return
        def fetch_one(tid):
            t0 = time.perf_counter()
            try: r = c.get("https://clob.polymarket.com/book", params={"token_id": tid}, timeout=8)
            except: return None
            return (time.perf_counter()-t0)*1000 if r.status_code==200 else None
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=20) as ex:
            results = [r for r in ex.map(fetch_one, tokens) if r]
        total = (time.perf_counter()-t0)*1000
        if results:
            print(f"  fetched {len(results)} books in {total:.0f}ms")
            print(f"  per-book: min={min(results):.0f} med={statistics.median(results):.0f} max={max(results):.0f} ms")
            print(f"  throughput: {len(results)/(total/1000):.1f} books/sec")

async def ws_test():
    banner("WEBSOCKET")
    try: import websockets
    except ImportError: print("  no websockets module"); return
    url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    try:
        t0 = time.perf_counter()
        async with websockets.connect(url, ping_interval=20) as ws:
            print(f"  connect: {(time.perf_counter()-t0)*1000:.0f}ms")
            await ws.send(json.dumps({"type":"MARKET","assets_ids":["86477388912240063425968488533648571842432556728263832735069050797247776619810"]}))
            t1 = time.perf_counter()
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=8)
                print(f"  first msg: {(time.perf_counter()-t1)*1000:.0f}ms")
            except asyncio.TimeoutError: print("  no msg in 8s")
    except Exception as e: print(f"  err: {e}")

print(f"# Latency baseline test — {datetime.now(timezone.utc).isoformat()}")
env_info()
public_ip_geo()
dns_resolve()
http_latency(20)
parallel_book()
asyncio.run(ws_test())
print("\n=== DONE ===")
