"""bt_loss_episodes_month.py — run the CURRENT z-maker signal over 30d, chronological, and find the
LOSS-CONCENTRATED episodes (drawdown stretches). Entry = late (min3-4) first-qualifying |lead|>=8 & z>=2.5
(btc+eth). Loss = clear reversal (settle sign != entry-lead sign) OR tight-call (|settle|<2.5bps ~ coinflip
at the favorite price, counted loss) -> approximates the REAL loss set (binance clear-only undercounts).
Then scan for episodes: rolling-10 of OUR entries with >=2 losses = the breaker-ON / loss-concentrated state."""
import math, time, statistics as st, httpx
from datetime import datetime, timezone
SYMS = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
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
SER = {c: fetch(s) for c, s in SYMS.items()}
def ownvol(ser, ws, m):
    m0 = ws+m*60; cl = [ser[m0-i*60][1] for i in range(31) if (m0-i*60) in ser]
    if len(cl) < 20: return None
    rr = [math.log(cl[i]/cl[i-1])*1e4 for i in range(1, len(cl))]; return st.pstdev(rr)
# generate chronological entries
ent = []
for coin in SYMS:
    ser = SER[coin]; ws = (t0+2400)//300*300
    while ws+300 <= t1:
        op = ser.get(ws); c4 = ser.get(ws+240)
        if op and c4:
            o = op[0]; settle = math.log(c4[1]/o)*1e4
            for m in (3, 4):
                cc = ser.get(ws+m*60)
                if not cc: continue
                l = math.log(cc[1]/o)*1e4
                if abs(l) < 8: continue
                v = ownvol(ser, ws, m)
                if not v or abs(l)/v < 2.5: continue
                clear_rev = (l >= 0) != (settle >= 0)
                tight = abs(settle) < 2.5
                loss = clear_rev or tight   # realistic loss proxy
                ent.append({"ws": ws, "loss": loss, "clear": clear_rev, "tight": tight}); break
        ws += 300
ent.sort(key=lambda e: e["ws"])
n = len(ent); nl = sum(1 for e in ent if e["loss"])
print(f"\n{n} entries over 30d ({n/30:.0f}/day) | loss-proxy rate={nl/n*100:.1f}% (clear-rev {sum(1 for e in ent if e['clear'])/n*100:.1f}% + tight-call {sum(1 for e in ent if e['tight'])/n*100:.1f}%)")
# breaker-ON state over the sequence: rolling-10 >=2 losses
on = 0; episodes = []; cur_start = None
for i in range(n):
    roll = sum(1 for e in ent[max(0, i-10):i] if e["loss"])
    if roll >= 2:
        on += 1
        if cur_start is None: cur_start = ent[i]["ws"]
    else:
        if cur_start is not None:
            episodes.append((cur_start, ent[i-1]["ws"])); cur_start = None
if cur_start is not None: episodes.append((cur_start, ent[-1]["ws"]))
print(f"\n=== LOSS-CONCENTRATED state (rolling-10 of our entries has >=2 losses = breaker-ON) ===")
print(f"  fraction of entries in loss-concentrated state: {on}/{n} = {on/n*100:.0f}%")
print(f"  number of distinct episodes: {len(episodes)}")
durs = [(e[1]-e[0])/3600 for e in episodes]
if durs:
    print(f"  episode duration (h): median={st.median(durs):.1f} max={max(durs):.1f} | total={sum(durs):.0f}h of ~{(t1-t0)/3600:.0f}h month")
print(f"\n=== the episodes (>=3h shown), by date ===")
for s, e in episodes:
    d = (e-s)/3600
    if d >= 3: print(f"  {datetime.fromtimestamp(s,timezone.utc).strftime('%m-%d %H:%M')} -> +{d:.0f}h")
print(f"\nREAD: ~X% of the month our strategy is in a loss-concentrated stretch; that's how often drawdowns")
print("like the last 2 days occur. The breaker downsizes the cell during exactly these stretches.")
