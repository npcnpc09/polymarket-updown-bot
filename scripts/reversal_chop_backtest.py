"""Test the user's idea: use REVERSAL COUNT (number of >=THR-bps swings) + MOMENTUM (|1h net|)
over the last hour as a CHOP/regime detector â€” does it SEPARATE winners from losers where 5m-scale
persist and 1h-ER could not? Uses our real DRY btc/eth entries (B, won) + binance for the swing count.
Split BY DAY for OOS. THR sweep. Cross reversals x momentum."""
import json,httpx,math,datetime
from collections import defaultdict
R=[]
for ln in open("data/multi_window_engine.jsonl",encoding="utf-8"):
    ln=ln.strip()
    if not ln: continue
    try: r=json.loads(ln)
    except: continue
    if r.get("coin") in ("btc","eth") and "won" in r and isinstance(r.get("B"),(int,float)):
        try: r["_st"]=int(r["slug"].split("-")[-1])
        except: continue
        R.append(r)
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}; sts=[r["_st"] for r in R]
def bn(sym,t0,t1):
    out={};cur=t0
    while cur<t1:
        k=httpx.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":t1*1000,"limit":1000},timeout=20).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=float(x[4])
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
BN={c:bn(SYM[c],min(sts)-3700,max(sts)+360) for c in SYM}
def series(c,t0,t1):
    d=BN[c]; out=[]
    for t in range(t0,t1,60):
        for dd in range(4):
            if t+dd in d: out.append(d[t+dd]); break
    return out
def reversals(ps,thr):
    if len(ps)<3: return 0
    cnt=0; direction=0; ext=ps[0]
    for p in ps[1:]:
        if direction==0:
            m=math.log(p/ext)*1e4
            if abs(m)>=thr: direction=1 if m>0 else -1; ext=p
        elif direction>0:
            if p>ext: ext=p
            elif math.log(p/ext)*1e4<=-thr: cnt+=1; direction=-1; ext=p
        else:
            if p<ext: ext=p
            elif math.log(p/ext)*1e4>=thr: cnt+=1; direction=1; ext=p
    return cnt
for r in R:
    ent=r["_st"]+180; ps=series(r["coin"],ent-3600,ent)
    r["_rev"]={thr:reversals(ps,thr) for thr in (15,20,30)}
    r["_mom"]=abs(math.log(ps[-1]/ps[0])*1e4) if len(ps)>=2 else 0
days=sorted(set(datetime.datetime.utcfromtimestamp(r["_st"]).strftime("%m-%d") for r in R))
def wr(rs): return (sum(1 for r in rs if r["won"])/len(rs)*100) if rs else 0
def ev(rs): return sum((5*(1-r["B"]) if r["won"] else -5*r["B"]) for r in rs)/len(rs) if rs else 0
print("DRY btc/eth entries:",len(R),"over",len(days),"days\n")
for thr in (15,20,30):
    print("=== reversal-count over last 1h, swing thr=%dbps ==="%thr)
    buckets=defaultdict(list)
    for r in R: buckets[min(r["_rev"][thr],6)].append(r)
    for k in sorted(buckets):
        s=buckets[k]
        print("  %d reversals: n=%-4d win=%2.0f%%  EV/order=%+.2f"%(k,len(s),wr(s),ev(s)))
    # does it SEPARATE? low-rev (trend) vs high-rev (chop)
    lo=[r for r in R if r["_rev"][thr]<=1]; hi=[r for r in R if r["_rev"][thr]>=3]
    print("  --> <=1 rev (trendy): n=%-3d win=%2.0f%% EV=%+.2f | >=3 rev (choppy): n=%-3d win=%2.0f%% EV=%+.2f"%(
        len(lo),wr(lo),ev(lo),len(hi),wr(hi),ev(hi)))
    # per-day OOS of the high-rev=worse claim
    pd=[]
    for dd in days:
        h=[r for r in R if r["_rev"][thr]>=3 and datetime.datetime.utcfromtimestamp(r["_st"]).strftime("%m-%d")==dd]
        l=[r for r in R if r["_rev"][thr]<=1 and datetime.datetime.utcfromtimestamp(r["_st"]).strftime("%m-%d")==dd]
        if h and l: pd.append("%s:%+.2fvs%+.2f"%(dd,ev(h),ev(l)))
    print("  per-day EV (choppy vs trendy):",pd,"\n")
# cross: high reversals AND low momentum = the 'pure chop' the user means
print("=== CROSS: reversals(thr8) x momentum(|1h net|) ===")
for rlab,rcond in (("<=1 rev",lambda r:r["_rev"][20]<=1),(">=3 rev",lambda r:r["_rev"][20]>=3)):
    for mlab,mcond in (("mom<25",lambda r:r["_mom"]<25),("mom>=25",lambda r:r["_mom"]>=25)):
        s=[r for r in R if rcond(r) and mcond(r)]
        if s: print("  %-8s & %-8s: n=%-3d win=%2.0f%% EV=%+.2f"%(rlab,mlab,len(s),wr(s),ev(s)))


