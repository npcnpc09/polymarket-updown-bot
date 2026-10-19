"""Does 'enter early + add on strengthening' concentrate on winners? For real windows (winner from ce25's
REDEEMs = real settlement), reconstruct the binance lead PATH (1s klines). Take the lead side at 60s (early
base), see if it STRENGTHENED by 150s, and compute REAL win rate split by strengthened vs faded. If
strengthened -> ~90%+ win, then eebde's add-on-strengthening loads winners (the early+add approach works);
if still ~72%, the confirmation signal doesn't help us."""
import json,os,math,time,statistics
import httpx
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
c=httpx.Client(timeout=20,headers={"User-Agent":"Mozilla/5.0"})
OUT=["Up","Down"]; SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
# real winners from ce25_full
RW={}
for l in open(os.path.join(ROOT,"data","ce25_full.jsonl"),encoding="utf-8"):
    r=json.loads(l); s=r.get("slug","")
    if "updown" not in s: continue
    w=RW.setdefault(s,{"buys":[],"ridx":None,"rsize":0.0})
    if r.get("type")=="TRADE" and r.get("side","").upper()=="BUY": w["buys"].append((r.get("outcome"),r.get("size") or 0))
    elif r.get("type")=="REDEEM":
        w["rsize"]+=r.get("size") or 0
        if r.get("outcomeIndex") is not None: w["ridx"]=r.get("outcomeIndex")
def winner(s):
    w=RW.get(s)
    if not w: return None
    if w["ridx"] in (0,1): return OUT[w["ridx"]]
    if w["rsize"]>0:
        up=sum(z for o,z in w["buys"] if o=="Up"); dn=sum(z for o,z in w["buys"] if o=="Down")
        return "Up" if abs(w["rsize"]-up)<abs(w["rsize"]-dn) else "Down"
    return None
# recent btc/eth 5m windows with a real winner
wins=[]
for s in RW:
    parts=s.split("-"); coin=parts[0]
    if coin not in SYM or "-5m-" not in s: continue
    try: st=int(parts[-1])
    except: continue
    if winner(s): wins.append((coin,st,winner(s)))
wins.sort(key=lambda x:-x[1]); wins=wins[:140]   # most recent 140
print("取 %d 个有真实结算的 btc/eth 5m窗口\n"%len(wins))
def lead_at(coin,st,off):
    sym=SYM[coin]
    try:
        k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1s","startTime":st*1000,"endTime":(st+off+5)*1000,"limit":1000}).json()
        if not isinstance(k,list) or not k: return None,None
        op=float(k[0][1]); tgt=None
        for x in k:
            if int(x[0]//1000)-st>=off: tgt=float(x[4]); break
        if tgt is None: tgt=float(k[-1][4])
        return op,tgt
    except: return None,None
rows=[]
for coin,st,win in wins:
    op,p60=lead_at(coin,st,60)
    if not op or not p60: continue
    _,p150=lead_at(coin,st,150)
    if not p150: continue
    l60=math.log(p60/op)*1e4; l150=math.log(p150/op)*1e4
    if abs(l60)<3: continue   # need an early lead to have a "side"
    side="Up" if l60>=0 else "Down"
    l60s=abs(l60); l150s=l150*(1 if side=="Up" else -1)  # toward the 60s side
    rows.append({"side":side,"l60":l60s,"l150":l150s,"strengthened":l150s>=l60s and l150s>=8,"won":side==win})
print("可分析 %d 个 (60s有lead>=3)\n"%len(rows))
def wr(rs,lbl):
    if not rs: print("  %-26s n=0"%lbl);return
    print("  %-26s n=%-4d 真实胜率 %2.0f%%"%(lbl,len(rs),sum(1 for r in rs if r["won"])/len(rs)*100))
print("=== 早入(60s领先侧) 真实胜率, 按是否走强到150s ===")
wr(rows,"全部60s领先侧")
wr([r for r in rows if r["strengthened"]],"走强(150s lead>=8且更强)")
wr([r for r in rows if not r["strengthened"]],"没走强/衰退")
print("\n=== 按 150s时的lead强度 (=加仓时的确认强度) ===")
wr([r for r in rows if r["l150"]<0],"150s已翻负(反转)")
wr([r for r in rows if 0<=r["l150"]<8],"150s弱 0-8")
wr([r for r in rows if 8<=r["l150"]<18],"150s中 8-18")
wr([r for r in rows if r["l150"]>=18],"150s强>=18")
