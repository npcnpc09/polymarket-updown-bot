"""OOS backtest of 'our momentum + eebde's money confirmation'. For each btc/eth 5m window in eebde's
7d history (05-23..05-28, separate from the recent in-sample overlap): compute OUR entry signal
(peak|lead| over min0-3 >= 15 AND |lead@min3| >= 8 = our cushion rule), eebde's VALUE-weighted favorite,
and the winner (binance net = Chainlink at >=5bps). Split OUR win rate by aligned-with-eebde vs against,
per day. If aligned stays ~88% and against ~42% here too, the signal is OOS-validated."""
import json,re,httpx,math,datetime
from collections import defaultdict
EF="data/eebde_history_7d.jsonl"
EV=defaultdict(lambda:defaultdict(float))
for ln in open(EF,encoding="utf-8"):
    ln=ln.strip()
    if not ln: continue
    try: r=json.loads(ln)
    except: continue
    if r.get("type")!="TRADE" or (r.get("side") or "").upper()!="BUY": continue
    m=re.match(r"(btc|eth)-updown-5m-(\d+)",r.get("slug","") or "")
    if not m or r.get("outcome") not in ("Up","Down"): continue
    EV[r["slug"]][r["outcome"]]+=(r.get("price",0) or 0)*(r.get("size",0) or 0)
def efav(s):
    d=EV.get(s); return max(d,key=d.get) if d else None
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
slugs=[s for s in EV]; sts=[int(s.split("-")[-1]) for s in slugs]
def bn(sym,t0,t1):
    out={};cur=t0
    while cur<t1:
        k=httpx.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":t1*1000,"limit":1000},timeout=20).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=float(x[4]); out[(int(x[0]//1000),"o")]=float(x[1])
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
BN={c:bn(SYM[c],min(sts)-120,max(sts)+400) for c in SYM}
def px(c,t):
    d=BN[c]
    for dd in range(3):
        if t+dd in d: return d[t+dd]
    return None
rows=[]
for s in slugs:
    c="btc" if s.startswith("btc") else "eth"; st=int(s.split("-")[-1])
    op=px(c,st); pe=px(c,st+180); cl=px(c,st+240) or px(c,st+300)
    if not(op and pe and cl): continue
    peak=0
    for mm in range(4):
        q=px(c,st+mm*60)
        if q: peak=max(peak,abs(math.log(q/op)*1e4))
    lead=math.log(pe/op)*1e4
    if peak<15 or abs(lead)<8: continue   # OUR entry: peak>=15 AND cushion |lead|>=8
    side="Up" if lead>=0 else "Down"
    won=(side=="Up")==(cl>=op)
    fav=efav(s)
    rows.append({"day":datetime.datetime.utcfromtimestamp(st).strftime("%m-%d"),"side":side,"won":won,
                 "fav":fav,"aligned":(fav==side) if fav else None})
def wr(rs): return sum(1 for r in rs if r["won"])/len(rs)*100 if rs else 0
days=sorted(set(r["day"] for r in rows))
print("OUR-signal windows (peak>=15 & |lead|>=8) with eebde data: %d over %d days\n"%(len(rows),len(days)))
al=[r for r in rows if r["aligned"]==True]; ag=[r for r in rows if r["aligned"]==False]
print("BASELINE (our signal, all): n=%-4d win=%.0f%%"%(len(rows),wr(rows)))
print("ALIGNED  with eebde fav   : n=%-4d win=%.0f%%"%(len(al),wr(al)))
print("AGAINST  eebde fav        : n=%-4d win=%.0f%%"%(len(ag),wr(ag)))
print("\nper-day (aligned win%% | against win%% | n_align/n_against):")
for dd in days:
    a=[r for r in al if r["day"]==dd]; b=[r for r in ag if r["day"]==dd]
    print("  %s: aligned %3.0f%% | against %3.0f%%  (%d / %d)"%(dd,wr(a),wr(b),len(a),len(b)))
