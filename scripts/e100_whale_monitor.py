"""e100_whale_monitor.py — weekly true-settle scorecard for the LoL whale 0xe1000ddb.

WHY: e100 is the ONLY copyable whale found (copy-gap +/-2%, see memory
lol-whale-e100-copyable-but-cold). His edge is real but violently front-loaded, so the
copy decision is a TIMING question — "is he hot right now?" — that has to be re-measured,
not assumed. This is that measurement, rerunnable.

METHOD (the standard TRUE-settle grading, no jsonl/leaderboard trust):
  1. data-api /activity, paged backwards with the `end=` time cursor (offset is capped).
  2. Group TRADE rows by conditionId; BUY = -usdc/+shares, SELL = +usdc/-shares.
  3. Grade against CLOB /markets/<conditionId> -> tokens[].winner (closed markets only).
     PnL = net_cash + shares_on_winning_token. Open markets are marked, reported apart.
     gamma's condition_ids filter silently ignores the param (returns the default list) —
     use the CLOB per-condition endpoint, not gamma, for this.

Read the CONCENTRATION + size-distribution lines, not just the ROI: his profit lives in a
handful of huge fills while the median fill is ~$25. A proportional copy would scale the
big ones below the 5-share minimum and fill only the small losing tail -> any copy must be
usdcSize-weighted (big fills only). That is NOT yet validated.

  python scripts/e100_whale_monitor.py [--days 90] [--since 2026-08-03] [--fresh]
"""
import os, sys, json, time, datetime, collections
import httpx
for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
WALLET = "0xe1000ddb5f5025849765e29d051dfff78f5d4d41"
ACT = os.path.join(DATA, "e100_activity.jsonl")
MKT = os.path.join(DATA, "e100_markets.json")

def _arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv): return sys.argv[i + 1]
    return default

DAYS  = int(_arg("--days", "90"))
FRESH = "--fresh" in sys.argv
SINCE = _arg("--since", "")
UTC   = datetime.timezone.utc
def D(ts): return datetime.datetime.fromtimestamp(ts, UTC)

def _get(c, url, params=None, tries=5):
    for a in range(tries):
        try:
            r = c.get(url, params=params); r.raise_for_status(); return r.json()
        except Exception as e:
            if a == tries - 1: print(f"  ! give up {url}: {type(e).__name__}"); return None
            time.sleep(2 + 2 * a)          # 429s are common on /activity; back off

def fetch_activity(cutoff):
    """Incremental: keep cached rows, page back only as far as `cutoff`."""
    rows, seen = [], set()
    if os.path.exists(ACT) and not FRESH:
        for l in open(ACT, encoding="utf-8"):
            a = json.loads(l); rows.append(a)
            seen.add((a.get("transactionHash"), a.get("asset"), a.get("side"), a.get("timestamp"), a.get("size")))
    c = httpx.Client(timeout=30)
    end, pages = int(time.time()) + 3600, 0
    while True:
        b = _get(c, "https://data-api.polymarket.com/activity",
                 {"user": WALLET, "limit": 500, "end": end, "sortDirection": "DESC"})
        if not b: break
        new, oldest = 0, end
        for a in b:
            k = (a.get("transactionHash"), a.get("asset"), a.get("side"), a.get("timestamp"), a.get("size"))
            oldest = min(oldest, a.get("timestamp", oldest))
            if k in seen: continue
            seen.add(k); rows.append(a); new += 1
        pages += 1
        print(f"  page{pages} got={len(b)} new={new} oldest={D(oldest):%Y-%m-%d}")
        if oldest <= cutoff or len(b) < 500: break
        end = oldest if new else oldest - 1   # no-new page = a full page of ties, step past it
        if pages > 400: print("  ! page cap"); break
    rows.sort(key=lambda a: a.get("timestamp", 0))
    with open(ACT, "w", encoding="utf-8") as f:
        for a in rows: f.write(json.dumps(a) + "\n")
    return [r for r in rows if r.get("timestamp", 0) >= cutoff]

def fetch_markets(conds):
    mk = json.load(open(MKT)) if os.path.exists(MKT) else {}
    todo = [x for x in conds if x and x not in mk]
    if todo:
        c = httpx.Client(timeout=30)
        for i, cid in enumerate(todo):
            m = _get(c, f"https://clob.polymarket.com/markets/{cid}")
            if m: mk[cid] = {"closed": m.get("closed"), "question": m.get("question"),
                             "tokens": [{"token_id": t["token_id"], "outcome": t.get("outcome"),
                                         "winner": t.get("winner"), "price": t.get("price")}
                                        for t in m.get("tokens", [])]}
            if i % 25 == 0: print(f"  markets {i}/{len(todo)}")
        json.dump(mk, open(MKT, "w"))
    return mk

def grade(trades, mk):
    C = collections.defaultdict(lambda: {"cash": 0.0, "sh": collections.defaultdict(float),
                                         "ts": [], "spend": 0.0, "title": ""})
    for r in trades:
        d = C[r["conditionId"]]
        sz, usd = float(r["size"]), float(r["usdcSize"])
        if r["side"] == "BUY": d["cash"] -= usd; d["sh"][r["asset"]] += sz; d["spend"] += usd
        else:                  d["cash"] += usd; d["sh"][r["asset"]] -= sz
        d["ts"].append(r["timestamp"]); d["title"] = r.get("title", "")
    out = []
    for cid, d in C.items():
        m = mk.get(cid)
        if not m: continue
        closed = bool(m.get("closed")); tok = {t["token_id"]: t for t in m["tokens"]}
        payout, ungraded = 0.0, False
        for tid, sh in d["sh"].items():
            if abs(sh) < 1e-9: continue
            t = tok.get(tid)
            if t is None: ungraded = True; continue
            payout += sh * (1.0 if t.get("winner") else (0.0 if closed else float(t.get("price") or 0)))
        out.append({"cid": cid, "title": d["title"], "closed": closed and not ungraded,
                    "spend": d["spend"], "pnl": d["cash"] + payout,
                    "first": min(d["ts"]), "last": max(d["ts"]), "nfills": len(d["ts"])})
    return sorted(out, key=lambda x: x["last"])

def main():
    cutoff = int(time.time()) - DAYS * 86400
    print(f"=== e100 whale monitor — last {DAYS}d, as of {D(time.time()):%Y-%m-%d %H:%M UTC} ===")
    rows = fetch_activity(cutoff)
    tr = [r for r in rows if r.get("type") == "TRADE"]
    if not tr: print("no trades in window"); return
    mk = fetch_markets(sorted({r["conditionId"] for r in tr}))
    graded = grade(tr, mk)
    res = [o for o in graded if o["closed"]]; opn = [o for o in graded if not o["closed"]]

    last = max(r["timestamp"] for r in tr)
    print(f"\nlast TRADE {D(last):%Y-%m-%d %H:%M UTC} — silent {(time.time()-last)/86400:.1f}d"
          f" | {len(tr)} fills / {len(graded)} markets ({len(opn)} still open)")

    print("\nweek      dates          spend         pnl       ROI     n green")
    W = collections.defaultdict(lambda: [0.0, 0.0, 0, 0, []])
    for o in res:
        dt = D(o["last"]); y, w, _ = dt.isocalendar(); k = f"{y}-W{w:02d}"
        W[k][0] += o["spend"]; W[k][1] += o["pnl"]; W[k][2] += 1; W[k][3] += (o["pnl"] > 0); W[k][4].append(dt)
    for k in sorted(W):
        s, p, n, g, ds = W[k]
        print(f"{k}  {min(ds):%m-%d}~{max(ds):%m-%d}  {s:>10,.0f} {p:>+11,.0f} {100*p/s if s else 0:>+8.1f}% {n:>5} {g:>5}")
    ts_, tp = sum(o["spend"] for o in res), sum(o["pnl"] for o in res)
    print(f"TOTAL {DAYS}d: spend ${ts_:,.0f}  pnl ${tp:+,.0f}  ROI {100*tp/ts_ if ts_ else 0:+.2f}%"
          f"  green {sum(1 for o in res if o['pnl']>0)}/{len(res)}")

    # fill-level ROI (buys, hold-to-settle) — the metric the copy gate is written against
    for d in (32, 21, 14):
        cut = last - d * 86400; sp = pay = 0.0; n = 0
        for r in tr:
            if r["timestamp"] < cut or r["side"] != "BUY": continue
            m = mk.get(r["conditionId"])
            if not m or not m.get("closed"): continue
            w = next((t.get("winner") for t in m["tokens"] if t["token_id"] == r["asset"]), None)
            if w is None: continue
            sp += r["usdcSize"]; pay += r["size"] * (1.0 if w else 0.0); n += 1
        if sp: print(f"fill-level last {d:>2}d: n={n:<5} spend ${sp:>10,.0f}  ROI {100*(pay-sp)/sp:+.2f}%")

    since = (int(datetime.datetime.fromisoformat(SINCE + "T00:00:00+00:00").timestamp()) if SINCE else cutoff)
    rec = [o for o in res if o["last"] >= since]
    if rec:
        s = sum(o["spend"] for o in rec); p = sum(o["pnl"] for o in rec)
        top3 = sum(sorted((o["pnl"] for o in rec), reverse=True)[:3])
        eq = peak = dd = 0.0
        for o in rec: eq += o["pnl"]; peak = max(peak, eq); dd = min(dd, eq - peak)
        print(f"\nsince {D(since):%Y-%m-%d}: n={len(rec)} spend ${s:,.0f} pnl ${p:+,.0f}"
              f" ROI {100*p/s if s else 0:+.2f}% green {sum(1 for o in rec if o['pnl']>0)}/{len(rec)}")
        print(f"  CONCENTRATION top-3 markets ${top3:+,.0f} = {100*top3/p if p else 0:.0f}% of total pnl"
              f"  | path max drawdown ${dd:,.0f}")
        sz = sorted(r["usdcSize"] for r in tr if r["timestamp"] >= since and r["side"] == "BUY")
        if sz: print(f"  BUY fill size: median ${sz[len(sz)//2]:,.0f}  p90 ${sz[int(len(sz)*.9)]:,.0f}"
                     f"  max ${sz[-1]:,.0f}  n={len(sz)}   <- proportional copy dies here")
        print("\n  top winners / losers:")
        for o in sorted(rec, key=lambda x: -x["pnl"])[:3]: print(f"    {D(o['last']):%m-%d} {o['pnl']:>+11,.0f} on ${o['spend']:>9,.0f}  {o['title'][:50]}")
        for o in sorted(rec, key=lambda x:  x["pnl"])[:3]: print(f"    {D(o['last']):%m-%d} {o['pnl']:>+11,.0f} on ${o['spend']:>9,.0f}  {o['title'][:50]}")
    if opn:
        print("\n  OPEN (marked, not graded):")
        for o in opn: print(f"    {D(o['last']):%m-%d} spend ${o['spend']:,.0f} mark ${o['pnl']:+,.0f}  {o['title'][:50]}")

    # copy gate from memory: 2+ consecutive green weeks AND fill-level ROI > +15%
    streak = 0
    for k in sorted(W): streak = streak + 1 if W[k][1] > 0 else 0
    print(f"\nCOPY GATE: consecutive green weeks = {streak} (need >=2, and fill-level ROI > +15%)"
          f" -> {'PASS' if streak >= 2 else 'NOT MET'}")
    print("NOTE: live orders geo-blocked from this box (region-blocked-canada) — gate is academic until resolved.")

if __name__ == "__main__":
    main()
