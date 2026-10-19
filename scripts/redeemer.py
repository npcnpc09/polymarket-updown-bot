"""redeemer.py — auto-redeem WON positions to USDC cash, hourly. Built 2026-07-08 after Polymarket's
own auto-redeem relayer degraded (redeem lag went 0.7min -> 30-300min at ~04:00 UTC 07-08). We have no
control over their relayer, so this reclaims winnings ourselves: poll redeemable positions with
curPrice==1 (won, worth $1/share, not yet cashed), call redeem_positions(condition_id) once each.
Skips losers (curPrice==0, worth $0 — redeeming them only burns gas). Dedups within a run so a
still-unswept condition isn't resubmitted every cycle. DRY default (lists only); --place = real on-chain
redeem (gasless via SDK). -> data/redeemer.log + data/redeemer.jsonl
"""
import os, sys, time, json, datetime
import httpx
for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except: pass
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACE = ("--place" in sys.argv)
POLL_SEC = 3600
MAX_PER_CYCLE = 40         # backstop: don't fire more than this many redeems in one pass
OUTF = os.path.join(ROOT, "data", "redeemer.jsonl")
LOG = os.path.join(ROOT, "data", "redeemer.log")
def now(): return time.time()
def log(m):
    line = f"[{datetime.datetime.utcnow().strftime('%m-%d %H:%M:%S')}] {m}"; print(line, flush=True)
    try: open(LOG, "a", encoding="utf-8").write(line + "\n")
    except: pass
def load_env():
    for l in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        if "=" in l and not l.startswith("#"):
            k, v = l.strip().split("=", 1); os.environ.setdefault(k.strip(), v.strip())
    return os.environ["POLY_PK"], os.environ["POLY_PROXY"]

def winners(proxy):
    """redeemable positions that WON (curPrice==1, real cash to claim)."""
    try:
        r = httpx.get("https://data-api.polymarket.com/positions",
                      params={"user": proxy, "limit": 500, "redeemable": "true"}, timeout=25).json()
    except Exception as e:
        log(f"positions err {str(e)[:60]}"); return []
    out = []
    for p in (r if isinstance(r, list) else []):
        try:
            if float(p.get("curPrice") or 0) == 1.0 and float(p.get("currentValue") or 0) > 0 and p.get("conditionId"):
                out.append((p["conditionId"], float(p["currentValue"]), p.get("slug", "")))
        except: pass
    return out

def main():
    pk, proxy = load_env()
    cli = None
    if PLACE:
        from polymarket import SecureClient
        cli = SecureClient.create(private_key=pk, wallet=proxy)
    log(f"redeemer START [{'LIVE --place' if PLACE else 'DRY (list only)'}] poll={POLL_SEC}s")
    while True:
        try:
            wins = winners(proxy)
            # dedup by conditionId (one redeem claims the whole winning condition)
            seen = {}
            for cid, val, slug in wins:
                seen[cid] = seen.get(cid, [0.0, ""]); seen[cid][0] += val; seen[cid][1] = slug
            total = round(sum(v[0] for v in seen.values()), 2)
            log(f"redeemable winners: {len(wins)} positions / {len(seen)} conditions, worth ${total:.2f}")
            done = 0
            for cid, (val, slug) in list(seen.items())[:MAX_PER_CYCLE]:
                if not PLACE:
                    log(f"  [DRY] would redeem {slug or cid[:12]} ${val:.2f}")
                    continue
                try:
                    h = cli.redeem_positions(condition_id=cid)
                    txh = getattr(h, "transaction_hash", None) or getattr(h, "hash", None) or str(h)[:24]
                    done += 1
                    log(f"  REDEEMED {slug or cid[:12]} ${val:.2f} tx={str(txh)[:20]}")
                    open(OUTF, "a", encoding="utf-8").write(json.dumps(
                        {"ts": int(now()), "cid": cid, "slug": slug, "val": round(val, 2), "tx": str(txh)[:66]}) + "\n")
                    time.sleep(1.5)
                except Exception as e:
                    log(f"  redeem err {slug or cid[:12]}: {str(e)[:70]}")
            if PLACE and done: log(f"cycle done: {done} conditions redeemed")
        except Exception as e:
            log(f"cycle err {str(e)[:70]}")
        time.sleep(POLL_SEC)

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: pass
