"""bt_eth_reversal_measures.py — do PRINCIPLED reversal measures (beyond plain vol) predict eth 5m
reversals? 30d eth. For each window with |lead@min3|>=8 (our late-entry profile), compute at entry from
PRIOR price action, then test reversal-rate (sign(lead@min3)!=sign(settle)) by measure bucket:
  VOL    : trailing-30m 1m-return stdev (baseline)
  VR5    : variance ratio q=5 (Lo-MacKinlay); <1 mean-reverting (reversal-prone)
  DC     : directional-change count in trailing 30m at theta=6bps (choppiness)
  JUMP   : jump share = max(0, RV-BV)/RV over trailing 30m (overreaction)
  SKEW   : skew of trailing-30m 1m returns
A measure that makes reversal-rate rise monotonically across its buckets = a real reversal predictor."""
import math, time, statistics as st, httpx
SYM = "ETHUSDT"
now = int(time.time()); t1 = now//60*60; t0 = t1 - 30*86400 - 2400
out = {}; cur = t0
print("fetching 30d eth 1m...")
with httpx.Client() as c:
    while cur < t1:
        r = c.get("https://api.binance.com/api/v3/klines", params={"symbol": SYM, "interval": "1m", "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
        if not isinstance(r, list) or not r: break
        for k in r: out[int(k[0]//1000)] = (float(k[1]), float(k[4]))
        cur = int(r[-1][0]//1000)+60
SER = out
def closes_before(ws, n):  # n 1m closes ending at window start
    m0 = ws//60*60; cl = [SER[m0-i*60][1] for i in range(n, -1, -1) if (m0-i*60) in SER]
    return cl
def measures(ws):
    cl = closes_before(ws, 30)
    if len(cl) < 25: return None
    r = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]
    if len(r) < 24: return None
    vol = st.pstdev(r)
    if vol == 0: return None
    # variance ratio q=5 (non-overlapping)
    q = 5; m = sum(r)/len(r)
    v1 = sum((x-m)**2 for x in r)/len(r)
    fives = [sum(r[i:i+q]) for i in range(0, len(r)-q+1, q)]
    if len(fives) >= 3 and v1 > 0:
        mf = sum(fives)/len(fives); vq = sum((x-mf)**2 for x in fives)/len(fives)
        vr = vq/(q*v1)
    else: vr = 1.0
    # directional changes at theta=6bps (count reversals from running extreme)
    theta = 6.0; dc = 0; ext = cl[0]; mode = 0  # 0 unknown,1 up,-1 down
    for px in cl[1:]:
        ch = math.log(px/ext)*1e4
        if mode <= 0 and ch >= theta: dc += 1; mode = 1; ext = px
        elif mode >= 0 and ch <= -theta: dc += 1; mode = -1; ext = px
        else:
            if mode == 1 and px > ext: ext = px
            if mode == -1 and px < ext: ext = px
    # jump share: bipower vs realized variance
    rv = sum(x*x for x in r); bv = (math.pi/2)*sum(abs(r[i])*abs(r[i-1]) for i in range(1, len(r)))
    jump = max(0.0, rv-bv)/rv if rv > 0 else 0
    # skew
    sd = vol; skew = (sum(((x-m)/sd)**3 for x in r)/len(r)) if sd > 0 else 0
    return {"vol": vol, "vr": vr, "dc": dc, "jump": jump, "skew": skew}

E = []
ws = (t0+2400)//300*300
while ws+300 <= t1:
    op = SER.get(ws); c3 = SER.get(ws+180); c4 = SER.get(ws+240)
    if op and c3 and c4:
        o = op[0]; lead3 = math.log(c3[1]/o)*1e4; settle = math.log(c4[1]/o)*1e4
        if abs(lead3) >= 8:
            mz = measures(ws)
            if mz: mz["rev"] = (lead3 >= 0) != (settle >= 0); E.append(mz)
    ws += 300
n = len(E); base = sum(1 for e in E if e["rev"])/n*100
print(f"\n{n} eth windows (|lead@min3|>=8) | baseline reversal-rate = {base:.1f}%\n")
def buckets(key, edges, lab):
    print(f"  {lab} (reversal% by bucket; monotonic = predictive):")
    for i in range(len(edges)+1):
        lo = edges[i-1] if i > 0 else -1e9; hi = edges[i] if i < len(edges) else 1e9
        s = [e for e in E if lo <= e[key] < hi]
        if len(s) >= 20:
            rv = sum(1 for e in s if e["rev"])/len(s)*100
            print(f"    {key} [{lo if lo>-1e8 else '-inf':>6},{hi if hi<1e8 else 'inf':>6}): n={len(s):4d} rev%={rv:5.1f}")
buckets("vol", [4, 6, 9], "VOL (baseline)")
buckets("vr", [0.6, 0.9, 1.2], "VR5 (<1 mean-revert)")
buckets("dc", [1, 3, 5], "DC (choppiness)")
buckets("jump", [0.1, 0.3, 0.5], "JUMP share")
buckets("skew", [-0.5, 0, 0.5], "SKEW")
print("\nVERDICT: if a measure's rev% rises monotonically & with a wide spread -> it predicts eth reversals")
print("(better than vol). If all ~flat near baseline -> reversals stay unpredictable (efficient market).")
