"""alt_exec_dry_15m_regime.py — 15m REGIME-SWITCH DRY (no orders). Forward-validates the month-backtest
finding (5760 windows): the actionable axis for 15m is PATH (trend vs chop), not vol.
At ~min9 (late window) classify regime from the lead trajectory (live-knowable):
  PATH : flips<=1 AND persist>=0.7  -> TREND   else CHOP   (persist=|lead_now|/peak)
  VOL  : btc_vol30 < 6.5 -> calm    else volatile          (label; volatile+chop = worst regime)
Regime gate:
  TREND -> LOOSE: enter on |lead|>=8 (trend itself is the signal); cell upsize @0.90-0.95 (20sh)
  CHOP  -> STRICT: enter only if |lead|>=8 AND z>=2.0 AND peak|lead|>=20  (lifts chop 90->94% in BT)
Also logs the FLAT current-strategy decision (z>=2.5 AND btc_vol<6.5) per window -> head-to-head in one
file. Reads REAL PM book for would-cost; settles on binance close. -> data/alt_exec_dry_15m_regime.jsonl
Baseline 5m DRY (alt_exec_dry.py) is UNTOUCHED."""
import asyncio, json, time, math, os, sys, statistics as st
import httpx
for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except: pass
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTF = os.path.join(ROOT, "data", "alt_exec_dry_15m_regime.jsonl")
LOG = os.path.join(ROOT, "data", "alt_exec_dry_15m_regime.log")
COINS = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
GAMMA = "https://gamma-api.polymarket.com/markets"
DUR_SEC = 900
LATE_START = 540; LATE_END = 840          # late window = min9..min14 (matches BT "late")
LEAD_TRIG = 8.0                            # min |lead| both regimes
Z_STRICT = 2.0; ML_STRICT = 20.0          # chop strict gate
VOL_CAP = 6.5                              # btc-vol label (calm/volatile)
Z_FLAT = 2.5                               # FLAT control = current live strategy (z>=2.5 & btcvol<6.5)
SHARES = 5; CELL_LO = 0.90; CELL_HI = 0.95; CELL_SHARES = 20
EARLY_START = 120; EARLY_END = 360; EARLY_CAP = 0.85   # EARLY-CHEAP comparison track: first cross min2-6 where maker bid+1c < 0.85 (old-live 15m profit was here)
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
        k = (await c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "startTime": st_*1000, "limit": 1}, timeout=8)).json()
        return float(k[0][1])
    except: return None
async def bvol(c, sym):
    try:
        k = (await c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "limit": 31}, timeout=8)).json()
        cl = [float(x[4]) for x in k]; rets = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]
        return st.pstdev(rets)
    except: return None
async def klc(c, sym, st_, off):
    try:
        k = (await c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "startTime": (st_+off)*1000, "limit": 1}, timeout=8)).json()
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
        ad = sum(s for p, s in asks if ba and p <= ba+0.02)
        bd = sum(s for p, s in bids if bb and p >= bb-0.02)   # bid-side depth (was missing -> bid_depth 100% null in this file; fixed 2026-07-01 for OFI data)
        return bb, ba, bd, ad
    except: return None, None, 0, 0

W = {}
async def main():
    log(f"alt_exec_dry_15m_regime START [REGIME-SWITCH DRY, no orders] late={LATE_START}-{LATE_END}s "
        f"TREND(flips<=1&persist>=0.7)->loose lead>={LEAD_TRIG} | CHOP->strict z>={Z_STRICT}&peak>={ML_STRICT} "
        f"| FLAT-ctrl z>={Z_FLAT}&btcvol<{VOL_CAP}")
    async with httpx.AsyncClient() as c:
        while True:
            t = now(); ws = int(t//DUR_SEC*DUR_SEC); btcvol = await bvol(c, "BTCUSDT")
            for coin, sym in COINS.items():
                slug = f"{coin}-updown-15m-{ws}"
                w = W.get(slug)
                if w is None:
                    op = await bopen(c, sym, ws)
                    if not op: continue
                    W[slug] = w = {"coin": coin, "sym": sym, "ws": ws, "slug": slug, "open": op,
                                   "minlead": {}, "peak": 0.0, "entered": False, "done": False,
                                   "e_entered": False, "up": None, "dn": None}
                off = t - ws
                px = await bpx(c, sym)
                if not px: continue
                lead = math.log(px/w["open"])*1e4
                w["peak"] = max(w["peak"], abs(lead))
                m = int(off//60)                      # window-minute; sample one lead per minute
                if m not in w["minlead"] and 0 <= m <= 14: w["minlead"][m] = lead
                # EARLY-CHEAP comparison track (data-only): first early cross (min2-6) where a maker bid+1c
                # would be CHEAP (<EARLY_CAP). Tests the old-live finding that 15m profit was early+cheap,
                # incl. the unresolved question — does a cheap early resting bid actually fill (or adverse-select)?
                if not w["e_entered"] and EARLY_START <= off <= EARLY_END and abs(lead) >= LEAD_TRIG:
                    eside = "Up" if lead >= 0 else "Down"
                    if w["up"] is None: w["up"], w["dn"] = await toks(c, slug)
                    etok = w["up"] if eside == "Up" else w["dn"]
                    ebb, eba, _, _ = await book(c, etok) if etok else (None, None, 0, 0)
                    epost = round(ebb+0.01, 3) if ebb else None
                    if epost is not None and epost < EARLY_CAP:
                        w["e_entered"] = True; w["e_tok"] = etok; w["e_maker_post"] = epost
                        w["e_entry"] = {"slug": slug, "coin": coin, "track": "early", "side": eside, "off": round(off),
                                        "lead": round(lead, 1), "peak": round(w["peak"], 1), "bid": ebb, "ask": eba, "maker_post": epost}
                        w["e_maker_filled"] = (eba is not None and eba <= epost)
                        log(f"[{coin}] EARLY-FIRE {eside} off{round(off)} lead{lead:+.0f} post={epost} (cheap<{EARLY_CAP})")
                # ENTRY: first late poll where a regime gate passes
                if not w["entered"] and LATE_START <= off <= LATE_END:
                    seq = [w["minlead"][k] for k in sorted(w["minlead"]) if k >= 1]
                    flips = sum(1 for i in range(1, len(seq)) if (seq[i] >= 0) != (seq[i-1] >= 0)) if len(seq) > 1 else 0
                    persist = round(abs(lead)/w["peak"], 2) if w["peak"] > 0 else 0.0
                    path_reg = "trend" if (flips <= 1 and persist >= 0.7) else "chop"
                    vol_reg = ("calm" if (btcvol is not None and btcvol < VOL_CAP) else "volatile") if btcvol is not None else "unk"
                    cvol = await bvol(c, sym); z = abs(lead)/cvol if cvol else 0
                    side = "Up" if lead >= 0 else "Down"
                    # regime gate
                    if abs(lead) < LEAD_TRIG:
                        gate = None
                    elif path_reg == "trend":
                        gate = "trend_loose"
                    elif z >= Z_STRICT and w["peak"] >= ML_STRICT:
                        gate = "chop_strict"
                    else:
                        gate = "chop_skip"
                    flat_ok = (btcvol is not None and btcvol < VOL_CAP) and z >= Z_FLAT and abs(lead) >= LEAD_TRIG
                    if gate is None and not flat_ok:
                        continue                       # nothing fires yet; keep polling within late window
                    w["entered"] = True
                    if w["up"] is None: w["up"], w["dn"] = await toks(c, slug)
                    up, dn = w["up"], w["dn"]; tok = up if side == "Up" else dn
                    bb, ba, bd, ad = await book(c, tok) if tok else (None, None, 0, 0)
                    maker_post = round(bb+0.01, 3) if bb else None
                    sh = CELL_SHARES if (maker_post is not None and CELL_LO <= maker_post < CELL_HI) else SHARES
                    w["entry"] = {"slug": slug, "coin": coin, "side": side, "off": round(off), "lead": round(lead, 1),
                                  "z": round(z, 2), "cvol": round(cvol, 2) if cvol else None, "btcvol": round(btcvol, 2) if btcvol else None,
                                  "flips": flips, "persist": persist, "peak": round(w["peak"], 1),
                                  "path_reg": path_reg, "vol_reg": vol_reg, "regime_gate": gate, "flat_ok": flat_ok,
                                  "bid": bb, "ask": ba, "bid_depth": round(bd), "ask_depth": round(ad), "maker_post": maker_post, "sh": sh}
                    w["tok"] = tok; w["maker_post"] = maker_post
                    w["maker_filled"] = (ba is not None and maker_post is not None and ba <= maker_post)
                    log(f"[{coin}] FIRE {side} off{round(off)} lead{lead:+.0f} z{z:.1f} peak{w['peak']:.0f} flips{flips} "
                        f"persist{persist} {path_reg}/{vol_reg} gate={gate} flat={flat_ok} ask={ba} post={maker_post}")
            # MAKER fill tracking for fired-unsettled windows
            for s in list(W.keys()):
                w = W[s]
                if w.get("done") or not w.get("entry") or w.get("maker_filled") or not w.get("tok"): continue
                if now()-w["ws"] > DUR_SEC+5: continue
                _, ba2, _, _ = await book(c, w["tok"])
                if ba2 is not None and w.get("maker_post") is not None and ba2 <= w["maker_post"]:
                    w["maker_filled"] = True
            # EARLY-track maker fill tracking (separate: side/token may differ from the late entry)
            for s in list(W.keys()):
                w = W[s]
                if w.get("done") or not w.get("e_entry") or w.get("e_maker_filled") or not w.get("e_tok"): continue
                if now()-w["ws"] > DUR_SEC+5: continue
                _, eba2, _, _ = await book(c, w["e_tok"])
                if eba2 is not None and w.get("e_maker_post") is not None and eba2 <= w["e_maker_post"]:
                    w["e_maker_filled"] = True
            # SETTLE
            for s in list(W.keys()):
                w = W[s]
                if w["done"] or now()-w["ws"] <= DUR_SEC+5: continue
                cl = await klc(c, w["sym"], w["ws"], 840)     # close of min14 = window-end price
                if cl is None and now()-w["ws"] < DUR_SEC+240: continue
                w["done"] = True
                settle = math.log(cl/w["open"])*1e4 if cl else 0
                if w.get("entry"):
                    e = w["entry"]; e["track"] = "late"
                    won = (settle > 0) == (e["side"] == "Up")
                    taker_pnl = None
                    if e["ask"]:
                        tp = min(e["ask"]+0.01, 0.99); taker_pnl = round(((1-tp) if won else -tp)*e["sh"], 2)
                    mfilled = bool(w.get("maker_filled")); mp = w.get("maker_post")
                    maker_pnl = round(((1-mp) if won else -mp)*e["sh"], 2) if (mfilled and mp is not None) else None
                    e.update({"won": won, "settle_bps": round(settle, 1), "taker_pnl": taker_pnl,
                              "maker_filled": mfilled, "maker_pnl": maker_pnl, "ts": w["ws"]})
                    open(OUTF, "a", encoding="utf-8").write(json.dumps(e)+"\n")
                    log(f"[{w['coin']}] SETTLE {e['side']} {'WON' if won else 'LOST'} {e['path_reg']}/{e['regime_gate']} "
                        f"taker={taker_pnl} maker={'fill '+str(maker_pnl) if mfilled else 'NO-FILL'} (flat_ok={e['flat_ok']})")
                if w.get("e_entry"):  # EARLY-CHEAP track (flat 5sh; cheap <0.85 so never a cell upsize)
                    ee = w["e_entry"]; ewon = (settle > 0) == (ee["side"] == "Up")
                    et_pnl = round(((1-min(ee["ask"]+0.01, 0.99)) if ewon else -min(ee["ask"]+0.01, 0.99))*SHARES, 2) if ee["ask"] else None
                    emf = bool(w.get("e_maker_filled")); emp = w.get("e_maker_post")
                    em_pnl = round(((1-emp) if ewon else -emp)*SHARES, 2) if (emf and emp is not None) else None
                    ee.update({"won": ewon, "settle_bps": round(settle, 1), "taker_pnl": et_pnl,
                               "maker_filled": emf, "maker_pnl": em_pnl, "ts": w["ws"]})
                    open(OUTF, "a", encoding="utf-8").write(json.dumps(ee)+"\n")
                    log(f"[{w['coin']}] SETTLE-EARLY {ee['side']} {'WON' if ewon else 'LOST'} post={emp} "
                        f"taker={et_pnl} maker={'fill '+str(em_pnl) if emf else 'NO-FILL'}")
                W.pop(s, None)
            await asyncio.sleep(20)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
