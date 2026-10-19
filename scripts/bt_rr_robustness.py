"""bt_rr_robustness.py — is the RR reversal-rate indicator a SOUND design or fragile/arbitrary?
Tests its predictive power on REAL fills across design choices:
  N (trailing qualifying windows): 8, 12, 20
  early reference point: min2 (current) vs min3 (entry-aligned)
  reversal definition: any sign flip vs only |settle|>=5bps (denoise tight-calls)
For each variant: real loss% in TOP tercile of RR vs BOTTOM tercile (spread = predictive power).
A sound indicator separates robustly across choices; a fragile one only works at one arbitrary setting."""
import json, re, math, time, statistics as st, httpx
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
BSYM = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
now = int(time.time()); t1 = now//60*60; t0 = t1 - 30*86400 - 2400
def fetch(sym):
    out = {}; cur = t0
    with httpx.Client() as c:
        while cur < t1:
            r = c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
            if not isinstance(r, list) or not r: break
            for k in r: out[int(k[0]//1000)] = (float(k[1]), float(k[4]))
            cur = int(r[-1][0]//1000)+60
    return out
print("fetching 30d btc+eth...")
SER = {c: fetch(s) for c, s in BSYM.items()}

def build_RR(coin, ref_min, denoise, N):
    """RR[ws] = frac of last N qualifying windows that reversed (early-ref vs settle), strictly before ws."""
    ser = SER[coin]; ws = (t0+2400)//300*300; hist = []; RR = {}
    while ws+300 <= t1:
        op = ser.get(ws); cref = ser.get(ws+ref_min*60); cend = ser.get(ws+240)
        if op and cref and cend:
            o = op[0]; early = math.log(cref[1]/o)*1e4; settle = math.log(cend[1]/o)*1e4
            qual = abs(early) >= 8
            rev = qual and ((early >= 0) != (settle >= 0)) and (abs(settle) >= 5 if denoise else True)
            recent = [h for h in hist if h["q"]][-N:]
            RR[ws] = (sum(1 for h in recent if h["r"])/len(recent)) if len(recent) >= max(5, N//2) else None
            hist.append({"q": qual, "r": rev})
        ws += 300
    return RR

# real fills
F = []
for o in (json.loads(l) for l in open(ROOT+"/data/early_taker_probe.jsonl", encoding="utf-8") if l.strip()):
    if o.get("kind") == "entry" and o.get("won") is not None:
        m = re.search(r"(btc|eth)-updown-5m-(\d+)", o.get("slug", ""))
        if m: F.append({"coin": m.group(1), "ws": int(m.group(2)), "won": bool(o["won"])})
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None:
        m = re.search(r"(btc|eth)-updown-5m-(\d+)", o.get("slug", ""))
        if m: F.append({"coin": m.group(1), "ws": int(m.group(2)), "won": bool(o["won"])})
print(f"{len(F)} real fills\n")

def evaluate(ref_min, denoise, N):
    RRc = {c: build_RR(c, ref_min, denoise, N) for c in BSYM}
    vals = []
    for f in F:
        rr = RRc[f["coin"]].get(f["ws"])
        if rr is not None: vals.append((rr, f["won"]))
    if len(vals) < 60: return None
    vals.sort(key=lambda x: x[0])
    k = len(vals)//3
    bot = vals[:k]; top = vals[-k:]
    bl = sum(1 for r, w in bot if not w)/len(bot)*100
    tl = sum(1 for r, w in top if not w)/len(top)*100
    return len(vals), bl, tl, tl-bl, top[0][0]

print(f"{'variant':38s} {'n':>4s} {'botRR loss%':>11s} {'topRR loss%':>11s} {'spread':>7s} {'topThr':>7s}")
for ref_min in (2, 3):
    for denoise in (False, True):
        for N in (8, 12, 20):
            r = evaluate(ref_min, denoise, N)
            if r:
                n, bl, tl, sp, thr = r
                lab = f"ref=min{ref_min} {'denoise' if denoise else 'raw    '} N={N:<2d}"
                flag = "  <-- strong" if sp >= 7 else ("  weak" if sp < 3 else "")
                print(f"  {lab:36s} {n:4d} {bl:11.1f} {tl:11.1f} {sp:+7.1f} {thr:7.2f}{flag}")
print("\nREAD: spread = top-tercile loss% minus bottom-tercile. If spread stays clearly +ve across N / ref /")
print("denoise -> RR is a SOUND, robust reversal-regime indicator. If it only works at one setting -> fragile.")
