"""bt_airpocket_interval.py — how often does a CELL air-pocket (20sh cell loss) occur?
(A) REAL-PM backtest over the ~6d updown_tokens window (btc+eth): late z>=2.5 entries landing in the
    0.90-0.95 cell band, REAL PM settlement -> count losses, intervals between them, project to a month.
(B) LIVE cross-check: the actual 20sh cell air-pockets (real money), their intervals, fires/day.
binance-only month is NOT used (it undercounts the tight-call reversal tail ~10x)."""
import json, re, math, statistics as st, httpx
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
BSYM = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
toks = {c: [] for c in BSYM}
for ln in open(ROOT+"/data/updown_tokens.jsonl", encoding="utf-8"):
    try: r = json.loads(ln)
    except: continue
    if r.get("dur") == 300 and r.get("coin") in BSYM: toks[r["coin"]].append(r)
def fetch(sym, t0, t1):
    out = {}; cur = t0
    with httpx.Client() as c:
        while cur < t1:
            r = c.get("https://api.binance.com/api/v3/klines", params={"symbol": sym, "interval": "1m", "startTime": cur*1000, "endTime": t1*1000, "limit": 1000}, timeout=20).json()
            if not isinstance(r, list) or not r: break
            for k in r: out[int(k[0]//1000)] = (float(k[1]), float(k[4]))
            cur = int(r[-1][0]//1000)+60
    return out
def ph(tok, st_):
    try:
        r = httpx.get("https://clob.polymarket.com/prices-history", params={"market": tok, "startTs": st_-120, "endTs": st_+460, "fidelity": "1"}, timeout=15).json()
        h = r.get("history", []) if isinstance(r, dict) else []
        return {int(x["t"]//60): float(x["p"]) for x in h}
    except: return {}
print("(A) REAL-PM cell air-pocket backtest (btc+eth, ~6d)...")
SER = {}
for c, s in BSYM.items():
    wl = sorted(toks[c], key=lambda r: r["start"]); SER[c] = fetch(s, wl[0]["start"]-1860, wl[-1]["start"]+460)
cell_fills = []   # (ws, won)
for coin in BSYM:
    ser = SER[coin]
    def job(r):
        st_ = r["start"]
        if st_ not in ser: return None
        o = ser[st_][0]; h = ph(r["up"], st_)
        if len(h) < 5: return None
        m0 = st_//60; up_win = h[max(h)] >= 0.5
        for m in (3, 4):
            cc = ser.get(st_+m*60)
            if not cc: continue
            lead = math.log(cc[1]/o)*1e4
            if abs(lead) < 8: continue
            cl = [ser[(m0+m-i)*60][1] for i in range(31) if (m0+m-i)*60 in ser]
            if len(cl) < 20: break
            cl = cl[::-1]; rets = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]; v = st.pstdev(rets)
            if not v or abs(lead)/v < 2.5: continue
            side_up = lead >= 0
            pm = None
            for d in range(0, 3):
                if (m0+m-d) in h: pm = h[m0+m-d]; break
            if pm is None: continue
            B = pm if side_up else (1-pm)
            if 0.90 <= B < 0.95:   # CELL band
                return (st_, (side_up == up_win))
            return None
        return None
    with ThreadPoolExecutor(max_workers=12) as ex:
        for r in ex.map(job, sorted(toks[coin], key=lambda x: x["start"])):
            if r: cell_fills.append(r)
cell_fills.sort()
spanA = (cell_fills[-1][0]-cell_fills[0][0])/86400
nA = len(cell_fills); lossA = [ws for ws, won in cell_fills if not won]
print(f"  cell fills={nA} over {spanA:.1f}d ({nA/spanA:.1f}/day) | losses(air-pockets)={len(lossA)} | loss-rate={len(lossA)/nA*100:.1f}%")
if len(lossA) >= 2:
    iv = [(lossA[i]-lossA[i-1])/3600 for i in range(1, len(lossA))]
    print(f"  air-pocket intervals (h): {[round(x) for x in iv]}")
    print(f"  mean interval = {st.mean(iv):.1f}h | => ~{nA/spanA*len(lossA)/nA*24:.2f}/day | ~{(len(lossA)/spanA)*30:.0f}/month")
print(f"  NOTE: assume-fill -> real maker fill is adverse-selected so LIVE air-pocket rate is HIGHER:")

print("\n(B) LIVE 20sh cell air-pockets (real money, the truth)...")
cl=[]
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl", encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None and o.get("sh")==20:
        m=re.search(r"-5m-(\d+)",o.get("slug",""))
        if m: cl.append((int(m.group(1)),bool(o["won"])))
cl.sort()
span=(cl[-1][0]-cl[0][0])/86400; n=len(cl); ap=[ws for ws,won in cl if not won]
print(f"  LIVE cell fills={n} over {span:.1f}d ({n/span:.1f}/day) | air-pockets={len(ap)} | loss-rate={len(ap)/n*100:.1f}%")
if len(ap)>=2:
    iv=[(ap[i]-ap[i-1])/3600 for i in range(1,len(ap))]
    print(f"  LIVE air-pocket times: {[datetime.fromtimestamp(x,timezone.utc).strftime('%m-%d %H:%M') for x in ap]}")
    print(f"  LIVE intervals (h): {[round(x,1) for x in iv]} | mean {st.mean(iv):.1f}h")
print(f"  LIVE rate => ~{len(ap)/span:.2f} air-pockets/day = 1 per {span/len(ap)*24:.0f}h = ~{len(ap)/span*30:.0f}/month")
print("\n  (frequency scales with cell FIRE rate, i.e. market activity; live 20sh-cell era = 06-13 onward)")
