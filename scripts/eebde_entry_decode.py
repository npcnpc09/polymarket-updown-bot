"""Decode eebde's favorite ENTRY logic from his 7d history. For each btc/eth 5m window:
- his favorite (value-weighted) side + the timeline of his loading (when cum crosses $100/$300/$1000)
- the underlying (binance) lead toward his favorite at 30/60/90/120/180s
Question: is he REACTIVE (commits AFTER the underlying already leads his side) or ANTICIPATORY (commits
BEFORE the lead is established)? Does his favorite = the early lead, or does he pick the eventual winner
before the underlying shows it? When does his direction 'lock in' vs the underlying signal?"""
import json,re,httpx,math,datetime,statistics
from collections import defaultdict
EF="data/eebde_history_7d.jsonl"
WT=defaultdict(list)
for ln in open(EF,encoding="utf-8"):
    ln=ln.strip()
    if not ln: continue
    try: r=json.loads(ln)
    except: continue
    if r.get("type")!="TRADE" or (r.get("side") or "").upper()!="BUY": continue
    m=re.match(r"(btc|eth)-updown-5m-(\d+)",r.get("slug","") or "")
    if not m or r.get("outcome") not in ("Up","Down"): continue
    WT[r["slug"]].append((r.get("timestamp",0),r.get("outcome"),r.get("price",0) or 0,r.get("size",0) or 0))
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
sts=[int(s.split("-")[-1]) for s in WT]
def bn(sym,t0,t1):
    out={};cur=t0
    while cur<t1:
        k=httpx.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":t1*1000,"limit":1000},timeout=20).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[4]))   # (open, close)
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
BN={c:bn(SYM[c],min(sts)-120,max(sts)+400) for c in SYM}
def leadbps(coin,st,sec):
    """signed underlying lead (bps) at `sec` into window, + = Up"""
    d=BN[coin]; o=d.get(st)
    if not o: return None
    # use close of the minute containing st+sec
    mt=st + (sec//60)*60
    p=d.get(mt)
    if not p: return None
    return math.log(p[1]/o[0])*1e4
# aggregate
commit_sec=[]; lead_at_commit=[]; react=0; antic=0; cnt=0
fav_eq_lead={30:0,60:0,90:0,120:0,180:0}; fav_eq_lead_n={30:0,60:0,90:0,120:0,180:0}
firsttrade_sec=[]
for slug,trs in WT.items():
    coin="btc" if slug.startswith("btc") else "eth"; st=int(slug.split("-")[-1])
    if not BN[coin].get(st): continue
    trs.sort(key=lambda x:x[0])
    cum=defaultdict(float); commit=None
    for ts,o,p,sz in trs:
        cum[o]+=p*sz
        if commit is None and cum[max(cum,key=cum.get)]>=300:
            commit=(ts-st, max(cum,key=cum.get))   # (sec, favorite-at-commit)
    if commit is None: continue
    fav=max(cum,key=cum.get)   # final favorite
    cnt+=1
    firsttrade_sec.append(trs[0][0]-st)
    csec,_=commit; commit_sec.append(csec)
    # signed lead toward FINAL favorite at commit time
    lc=leadbps(coin,st,max(0,min(299,csec)))
    if lc is not None:
        toward = lc if fav=="Up" else -lc
        lead_at_commit.append(toward)
        if toward>=3: react+=1      # underlying already led his side -> reactive
        elif toward<=-3: antic+=1   # underlying led AGAINST his side -> he's anticipating a reversal
    # does his FINAL favorite match the underlying lead at 30/60/.../180s?
    for s in (30,60,90,120,180):
        l=leadbps(coin,st,s)
        if l is None or abs(l)<2: continue
        fav_eq_lead_n[s]+=1
        if (l>=0)==(fav=="Up"): fav_eq_lead[s]+=1
print("decoded windows:",cnt,"\n")
print("=== 他何时建仓 (favorite累计过$300的时点) ===")
print("  首笔交易: 中位 %ds | 累计过$300(实质承诺): 中位 %ds (范围 %d-%d)"%(
    statistics.median(firsttrade_sec),statistics.median(commit_sec),min(commit_sec),max(commit_sec)))
print("\n=== 承诺时刻, 标的领先他favorite方向多少bps ===")
print("  中位 %+.1f bps | >0=标的已领先他这侧(反应), <0=标的还领反向(预判)"%statistics.median(lead_at_commit))
print("  反应型(承诺时标的已领先他侧>=3bps): %d (%.0f%%)"%(react,react/(react+antic)*100 if react+antic else 0))
print("  预判型(承诺时标的还领反向>=3bps):   %d (%.0f%%)"%(antic,antic/(react+antic)*100 if react+antic else 0))
print("\n=== 他最终favorite = 标的在各时点领先方 的比例 (他多早锁定正确方向) ===")
for s in (30,60,90,120,180):
    if fav_eq_lead_n[s]: print("  %ds: %.0f%% (n=%d)"%(s,fav_eq_lead[s]/fav_eq_lead_n[s]*100,fav_eq_lead_n[s]))
