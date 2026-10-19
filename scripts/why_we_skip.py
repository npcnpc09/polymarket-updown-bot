"""For eebde's HEAVY-bet windows (final>=1500), reconstruct OUR self-taker conditions (peak_lead,
entry |lead|, accel, our-side vs his-favorite) from binance, and categorize WHY we'd skip: max_lead<15?
cushion<8? accel<=0? wrong side? = 'why he bet and we didn't'. Hourly."""
import json,re,httpx,math,datetime
from collections import defaultdict
# eebde heavy windows + favorite
EH={}
for fn in ("data/copy_cum_live.jsonl","data/copy_cum.jsonl"):
    try:
        for l in open(fn,encoding="utf-8"):
            l=l.strip()
            if not l: continue
            try: r=json.loads(l)
            except: continue
            if r.get("slug") and r.get("side") and r.get("final_cum",0)>=1500:
                EH[r["slug"]]={"fav":r["side"],"final":r["final_cum"]}
    except FileNotFoundError: pass
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
sts=[int(s.split("-")[-1]) for s in EH]
if not sts: print("无eebde重注窗口数据"); raise SystemExit
def bn(sym,t0,t1):
    out={};cur=t0
    while cur<t1:
        k=httpx.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":cur*1000,"endTime":t1*1000,"limit":1000},timeout=20).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=(float(x[1]),float(x[4]))
        cur=int(k[-1][0]//1000)+60
        if len(k)<1000: break
    return out
BN={c:bn(SYM[c],min(sts)-120,max(sts)+360) for c in SYM}
cats=defaultdict(int); byhr=defaultdict(lambda:defaultdict(int))
rows=[]
for slug,e in EH.items():
    coin="btc" if slug.startswith("btc") else "eth"; st=int(slug.split("-")[-1]); d=BN[coin]
    o=d.get(st)
    if not o: continue
    op=o[0]
    def lead(sec):
        pm=d.get(st+sec)
        return math.log(pm[1]/op)*1e4 if pm else None
    leads=[lead(s) for s in (0,60,120)]
    le=lead(120)  # ~entry lead proxy (min2-3)
    if le is None or leads[0] is None: continue
    peak=max(abs(x) for x in leads if x is not None)
    side="Up" if le>=0 else "Down"
    accel=(le-leads[0])*(1 if le>=0 else -1)
    hr=datetime.datetime.utcfromtimestamp(st).strftime("%H")
    # 我们自营会进吗? 按顺序找第一个挡住的
    if side!=e["fav"]: cat="方向≠他favorite"
    elif peak<15: cat="峰值领先<15"
    elif abs(le)<8: cat="入场领先<8(垫子)"
    elif accel<=0: cat="accel<=0(领先没加强)"
    else: cat="✓会进"
    cats[cat]+=1; byhr[hr][cat]+=1
    rows.append((hr,slug,side,e["fav"],peak,le,accel,cat))
print("eebde重注(>=1500)窗口: %d\n"%len(rows))
print("=== 我们为什么没下 (卡在哪) ===")
for c,n in sorted(cats.items(),key=lambda x:-x[1]):
    print("  %-22s %d (%.0f%%)"%(c,n,n/len(rows)*100))
print("\n=== 逐小时 ===")
for hr in sorted(byhr):
    d=byhr[hr]; tot=sum(d.values()); ok=d.get("✓会进",0)
    print("  %sh: 他重注%d个, 我们会进%d个 | 卡点: %s"%(hr,tot,ok,{k:v for k,v in d.items() if k!="✓会进"}))
