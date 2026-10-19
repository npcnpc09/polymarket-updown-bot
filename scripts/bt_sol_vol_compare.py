"""bt_sol_vol_compare.py — is SOL more volatile / choppier / more reversal-prone than btc/eth?
~7d of 1m klines per coin. Metrics:
  VOL    : mean 1m realized vol (stdev of 1m log-returns, bps/min) — AMPLITUDE
  |ret|  : mean abs 1m return (bps) — typical per-minute move
  AC1    : lag-1 autocorrelation of 1m returns — NEGATIVE = mean-reverting/choppy (whips), +=trending
  ER     : mean Kaufman efficiency ratio over 5m windows — LOW = choppy path (net move small vs path)
  REV%   : of 5m windows with |lead@min2|>=8, fraction where settle FLIPS sign — direct reversal rate
A coin that is higher-vol AND choppier (low ER, neg AC1, high REV%) reverses more -> adverse maker fills."""
import math, time, statistics as st, httpx
SYMS = {"btc": "BTCUSDT", "eth": "ETHUSDT", "sol": "SOLUSDT"}
now = int(time.time()); t1 = now//60*60; t0 = t1 - 7*86400 - 200
def fetch(sym):
    out = {}; cur = t0
    with httpx.Client() as c:
        while cur < t1:
            r = c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
            if not isinstance(r, list) or not r: break
            for k in r: out[int(k[0]//1000)] = (float(k[1]), float(k[4]))
            cur = int(r[-1][0]//1000)+60
    return out
print("fetching 7d btc+eth+sol...")
SER = {c: fetch(s) for c, s in SYMS.items()}
print(f"{'coin':4s} {'VOL(bps/min)':>13s} {'|ret|':>7s} {'AC1':>7s} {'ER(5m)':>7s} {'REV%':>6s} {'vol/btc':>8s}")
btcvol = None
res = {}
for coin, sym in SYMS.items():
    ser = SER[coin]; mins = sorted(ser)
    closes = [ser[m][1] for m in mins]
    rets = [math.log(closes[i]/closes[i-1])*1e4 for i in range(1, len(closes))]
    vol = st.pstdev(rets); absret = sum(abs(r) for r in rets)/len(rets)
    # lag-1 autocorr
    m = st.mean(rets); num = sum((rets[i]-m)*(rets[i-1]-m) for i in range(1, len(rets))); den = sum((x-m)**2 for x in rets)
    ac1 = num/den if den else 0
    # ER over 5m windows + reversal rate
    ers = []; rev = qual = 0
    base = (t0+200)//300*300; ws = base
    while ws+300 <= t1:
        seq = [ser[ws+k*60][1] for k in range(0, 6) if (ws+k*60) in ser]
        if len(seq) >= 5:
            net = abs(seq[-1]-seq[0]); path = sum(abs(seq[i]-seq[i-1]) for i in range(1, len(seq)))
            if path: ers.append(net/path)
            o = seq[0]; early = math.log(seq[min(2, len(seq)-1)]/o)*1e4; settle = math.log(seq[-1]/o)*1e4
            if abs(early) >= 8:
                qual += 1
                if (early >= 0) != (settle >= 0): rev += 1
        ws += 300
    er = sum(ers)/len(ers) if ers else 0; revpct = rev/qual*100 if qual else 0
    res[coin] = {"vol": vol, "absret": absret, "ac1": ac1, "er": er, "revpct": revpct, "qual": qual}
    if coin == "btc": btcvol = vol
for coin in SYMS:
    r = res[coin]
    print(f"{coin:4s} {r['vol']:13.2f} {r['absret']:7.2f} {r['ac1']:+7.3f} {r['er']:7.3f} {r['revpct']:5.1f}% {r['vol']/btcvol:7.2f}x")
print("\nREAD: SOL vol/btc >1 => SOL has bigger swings. Higher REV% / lower ER / more-negative AC1 => SOL")
print("reverses more = the late maker bid fills on more reversals = the -10pp adverse-fill gap we saw live.")
