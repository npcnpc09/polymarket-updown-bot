"""Reconcile REAL on-chain PnL for our wallet vs what the bots claimed. Bots compute PnL from binance kwin;
actual settlement is Chainlink -> tight-call windows can disagree (bot says WON, chain says LOST). Pull our
wallet /activity (TRADE buys with real prices + REDEEM payouts = real wins), bucket by slug: real PnL per
window = redeem_payout - buy_cost. Shows WHERE the loss is (biggest-loser windows) on REAL data, and the
binance-vs-chainlink gap (windows we bought but never redeemed = actually LOST despite bot maybe claiming win).
Reads POLY_PROXY only (never prints the key)."""
import os,json,time,sys
import httpx
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
proxy=None
for l in open(os.path.join(ROOT,".env"),encoding="utf-8"):
    if l.strip().startswith("POLY_PROXY"): proxy=l.strip().split("=",1)[1].strip()
if not proxy: print("no POLY_PROXY"); sys.exit()
print("wallet %s...%s\n"%(proxy[:6],proxy[-4:]))
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
A=[]
for off in range(0,1500,500):
    try: a=c.get("https://data-api.polymarket.com/activity",params={"user":proxy,"limit":500,"offset":off}).json()
    except Exception as e: print("err",e); break
    if not isinstance(a,list) or not a: break
    A+=a
    if len(a)<500: break
# session start ~ when bots launched today; keep updown 5m/15m only, recent
SINCE=int(time.time())-6*3600
win={}
for x in A:
    if not isinstance(x,dict): continue
    ts=x.get("timestamp") or 0
    if ts<SINCE: continue
    s=x.get("slug","")
    if "updown" not in s: continue
    w=win.setdefault(s,{"buy_cost":0.0,"buy_sh":0.0,"redeem":0.0,"n_buy":0})
    typ=x.get("type")
    if typ=="TRADE" and (x.get("side") or "").upper()=="BUY":
        w["buy_cost"]+=(x.get("price") or 0)*(x.get("size") or 0); w["buy_sh"]+=x.get("size") or 0; w["n_buy"]+=1
    elif typ=="REDEEM":
        w["redeem"]+=x.get("usdcSize") or x.get("size") or 0
rows=[]
for s,w in win.items():
    if w["n_buy"]==0: continue
    pnl=w["redeem"]-w["buy_cost"]
    rows.append({"slug":s,"cost":w["buy_cost"],"sh":w["buy_sh"],"redeem":w["redeem"],"pnl":pnl,"won":w["redeem"]>0.01})
rows.sort(key=lambda r:r["pnl"])
tot_cost=sum(r["cost"] for r in rows); tot_redeem=sum(r["redeem"] for r in rows); tot_pnl=tot_redeem-tot_cost
won=[r for r in rows if r["won"]]; lost=[r for r in rows if not r["won"]]
print("=== 链上真实对账 (近6h, updown) ===")
print("买入窗 %d | 赢(有redeem) %d | 输(无redeem) %d"%(len(rows),len(won),len(lost)))
print("总买入成本 $%.2f | 总赎回 $%.2f | \033[1m真实净PnL $%+.2f\033[0m\n"%(tot_cost,tot_redeem,tot_pnl))
print("输掉的窗总成本(全损): $%.2f  (%d窗买了但没赢)"%(sum(r["cost"] for r in lost),len(lost)))
print("赢的窗净赚: $%+.2f\n"%(sum(r["pnl"] for r in won)))
print("=== 亏最多的10窗 ===")
for r in rows[:10]:
    print("  %-28s 买$%.2f(%.0fsh) 赎$%.2f pnl=\033[1m%+.2f\033[0m %s"%(r["slug"][-28:],r["cost"],r["sh"],r["redeem"],r["pnl"],"赢" if r["won"] else "全损"))
