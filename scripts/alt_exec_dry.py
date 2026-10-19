"""alt_exec_dry.py — EXECUTION DRY for the 5 coins under the CURRENT strategy.
Reconstructs the current entry logic (|lead|>=8 first-cross within 180s, 15s confirm, btc_vol<6.5,
z=|lead|/coin_vol30 >= 2.5) and, when it fires, reads the REAL Polymarket book (ask, bid, spread,
depth) — the execution cost the current strategy would actually face. Places NO orders (zero cost).
At settle it records: won (binance close vs open), would_pnl as TAKER (pay ask) and as MAKER (post
bid+1c, filled only if a pullback reached it — approximated as filled if min-price-in-window <= bid+1c).
-> data/alt_exec_dry.jsonl . Light polling (every 25s, PM book only queried on a confirmed cross)."""
import asyncio, json, time, math, os, sys, statistics as st
import httpx
for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except: pass
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def _argval(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv): return sys.argv[i + 1]
    return default
# --dur lets a SEPARATE instance observe a different window length (e.g. 15m) without touching the 5m instance.
# Default 5m = UNCHANGED. 15m instance: --dur 15m (window 900s, btc/eth only, files _15m suffix).
DUR = _argval("--dur", "5m")
DUR_SEC = {"5m": 300, "15m": 900}[DUR]
_sfx = "" if DUR == "5m" else "_" + DUR
OUTF = os.path.join(ROOT, "data", f"alt_exec_dry{_sfx}.jsonl")
LOG = os.path.join(ROOT, "data", f"alt_exec_dry{_sfx}.log")
_ALLC = {"btc": "BTCUSDT", "eth": "ETHUSDT", "sol": "SOLUSDT", "xrp": "XRPUSDT", "doge": "DOGEUSDT", "bnb": "BNBUSDT"}
# 15m: btc/eth + the tight-spread alt candidates sol/xrp (2026-06-16: signal parity ~96% all coins, but
# spread gates — sol/xrp 15m = 1c (viable), doge 11c / bnb 5c EXCLUDED (maker can't capture). 5m: all 6.
COINS = ({"btc": "BTCUSDT", "eth": "ETHUSDT", "sol": "SOLUSDT", "xrp": "XRPUSDT"} if DUR == "15m" else _ALLC)
GAMMA = "https://gamma-api.polymarket.com/markets"
LEAD_TRIG = 8.0; CONFIRM_SEC = 15; MAX_OFFSET = int(DUR_SEC * 0.6); VOL_CAP = 6.5; ENTRY_Z = 2.5; SHARES = 5
def now(): return time.time()
def log(m):
    line = f"[{time.strftime('%H:%M:%S', time.gmtime())}] {m}"; print(line, flush=True)
    try: open(LOG, "a", encoding="utf-8").write(line + "\n")
    except: pass

async def bpx(c, sym):
    try:
        r = await c.get("https://api.binance.com/api/v3/ticker/price", params={"symbol": sym}, timeout=8)
        return float(r.json()["price"])
    except: return None
async def bopen(c, sym, st_):
    try:
        k = (await c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "startTime": st_ * 1000, "limit": 1}, timeout=8)).json()
        return float(k[0][1])
    except: return None
async def bvol(c, sym):
    try:
        k = (await c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "limit": 31}, timeout=8)).json()
        cl = [float(x[4]) for x in k]; rets = [math.log(cl[i] / cl[i - 1]) * 1e4 for i in range(1, len(cl))]
        return st.pstdev(rets)
    except: return None
async def klc(c, sym, st_, off):  # close price at st_+off via 1m
    try:
        k = (await c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "startTime": (st_ + off) * 1000, "limit": 1}, timeout=8)).json()
        return float(k[0][4])
    except: return None
async def toks(c, slug):
    try:
        arr = (await c.get(GAMMA, params={"slug": slug}, timeout=10)).json()
        if arr:
            ids = json.loads(arr[0]["clobTokenIds"]); outs = json.loads(arr[0]["outcomes"])
            return ids[outs.index("Up")], ids[outs.index("Down")]
    except: pass
    return None, None
async def book(c, tok):
    try:
        b = (await c.get("https://clob.polymarket.com/book", params={"token_id": tok}, timeout=8)).json()
        bids = sorted((float(x["price"]), float(x["size"])) for x in b.get("bids", []) if float(x["size"]) > 0 and 0 < float(x["price"]) < 1)
        asks = sorted((float(x["price"]), float(x["size"])) for x in b.get("asks", []) if float(x["size"]) > 0 and 0 < float(x["price"]) < 1)
        bb = bids[-1][0] if bids else None; ba = asks[0][0] if asks else None
        ad = sum(s for p, s in asks if ba and p <= ba + 0.02); bd = sum(s for p, s in bids if bb and p >= bb - 0.02)
        return bb, ba, bd, ad
    except: return None, None, 0, 0

W = {}
async def main():
    log(f"alt_exec_dry START [{DUR} EXECUTION DRY {list(COINS)}, no orders] lead>={LEAD_TRIG} z>={ENTRY_Z} btc_vol<{VOL_CAP} maxoff={MAX_OFFSET}")
    async with httpx.AsyncClient() as c:
        while True:
            t = now(); ws = int(t // DUR_SEC * DUR_SEC)
            btcvol = await bvol(c, "BTCUSDT")
            for coin, sym in COINS.items():
                slug = f"{coin}-updown-{DUR}-{ws}"
                w = W.get(slug)
                if w is None:
                    op = await bopen(c, sym, ws)
                    if not op: continue
                    W[slug] = w = {"coin": coin, "sym": sym, "ws": ws, "slug": slug, "open": op, "cross": None, "entered": False, "done": False, "lo": op, "hi": op}
                off = t - ws
                px = await bpx(c, sym)
                if not px: continue
                w["lo"] = min(w["lo"], px); w["hi"] = max(w["hi"], px)
                lead = math.log(px / w["open"]) * 1e4
                # PHASE1: first cross
                if w["cross"] is None and abs(lead) >= LEAD_TRIG and off <= MAX_OFFSET:
                    w["cross"] = {"t": t, "side": "Up" if lead > 0 else "Down", "lead": lead, "off": off}
                # PHASE2: confirm + read REAL book
                elif w["cross"] and not w["entered"] and t >= w["cross"]["t"] + CONFIRM_SEC:
                    cr = w["cross"]; lead2 = lead
                    same = (lead2 > 0) == (cr["side"] == "Up")
                    if abs(lead2) >= LEAD_TRIG and same:
                        cvol = await bvol(c, sym); z = abs(lead2) / cvol if cvol else 0
                        gate_ok = (btcvol is not None and btcvol < VOL_CAP) and z >= ENTRY_Z
                        up, dn = await toks(c, slug); tok = up if cr["side"] == "Up" else dn
                        bb, ba, bd, ad = await book(c, tok) if tok else (None, None, 0, 0)
                        maker_post = round(bb + 0.01, 3) if bb else None
                        w["entry"] = {"side": cr["side"], "lead": round(cr["lead"], 1), "lead2": round(lead2, 1), "off": round(cr["off"]),
                                      "z": round(z, 2), "cvol": round(cvol, 2) if cvol else None, "btcvol": round(btcvol, 2) if btcvol else None,
                                      "gate_ok": gate_ok, "bid": bb, "ask": ba, "spread": round(ba - bb, 3) if (bb and ba) else None,
                                      "bid_depth": round(bd), "ask_depth": round(ad), "maker_post": maker_post}
                        # MAKER fill model: we'd post a BUY at bid+1c; it fills if the ask later pulls back down
                        # to touch maker_post during the window. Track min_ask over the window post-entry.
                        w["tok"] = tok; w["maker_post"] = maker_post
                        w["min_ask"] = ba; w["maker_filled"] = (ba is not None and maker_post is not None and ba <= maker_post)
                        w["entered"] = True
                        log(f"[{coin}] FIRE {cr['side']} lead{lead2:+.0f} z{z:.1f} gate={gate_ok} ask={ba} post={maker_post} spread={w['entry']['spread']} adepth={ad}")
                    else:
                        w["entered"] = True; w["entry"] = None  # faded
            # MAKER fill-tracking pass: for fired-but-unsettled windows, re-poll the favorite book and
            # mark maker_filled if the ask has pulled back to our posted bid+1c (a real maker fill).
            for s in list(W.keys()):
                w = W[s]
                if w.get("done") or not w.get("entry") or w.get("maker_filled") or not w.get("tok"): continue
                if now() - w["ws"] > DUR_SEC + 5: continue
                _, ba2, _, _ = await book(c, w["tok"])
                if ba2 is not None:
                    _prev = w.get("min_ask")
                    w["min_ask"] = ba2 if _prev is None else min(_prev, ba2)
                    if w.get("maker_post") is not None and ba2 <= w["maker_post"]:
                        w["maker_filled"] = True
            # SETTLE pass: any tracked window whose 5m has ended (>305s after its OWN start)
            for s in list(W.keys()):
                w = W[s]
                if w["done"] or now() - w["ws"] <= DUR_SEC + 5: continue
                cl = await klc(c, w["sym"], w["ws"], DUR_SEC)
                if cl is None and now() - w["ws"] < DUR_SEC + 240: continue
                w["done"] = True
                if w.get("entry"):
                    e = w["entry"]; settle = math.log(cl / w["open"]) * 1e4 if cl else 0
                    won = (settle > 0) == (e["side"] == "Up")
                    taker_pnl = None
                    if e["ask"]:
                        tp = min(e["ask"] + 0.01, 0.99)
                        taker_pnl = round(((1 - tp) if won else -tp) * SHARES, 2)
                    # MAKER: only counts as a trade if our bid+1c filled (ask pulled back to it during window)
                    mfilled = bool(w.get("maker_filled")); mp = w.get("maker_post")
                    maker_pnl = round(((1 - mp) if won else -mp) * SHARES, 2) if (mfilled and mp is not None) else None
                    e.update({"won": won, "settle_bps": round(settle, 1), "taker_pnl": taker_pnl,
                              "maker_filled": mfilled, "maker_pnl": maker_pnl, "min_ask": w.get("min_ask"),
                              "slug": w["slug"], "ts": w["ws"]})
                    open(OUTF, "a", encoding="utf-8").write(json.dumps(e) + "\n")
                    log(f"[{w['coin']}] SETTLE {e['side']} {'WON' if won else 'LOST'} taker={taker_pnl} maker={'fill '+str(maker_pnl) if mfilled else 'NO-FILL'} (gate={e['gate_ok']})")
                W.pop(s, None)
            await asyncio.sleep(25)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
