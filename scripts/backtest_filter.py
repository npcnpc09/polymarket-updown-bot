"""Backtest the CURRENT early_taker filter on the past-days real data (alltrader_fills_real.json = real prices x
real redeem outcomes, ~600 btc/eth 5m windows). Filter = lead>=LEAD_TRIG toward bought side, offset<=MAX_OFFSET,
price<PRICE_CAP; per window take the EARLIEST qualifying fill (one position/window), hold to settle. Reports
n, win%, net EV/share, total PnL. Then sweeps PRICE_CAP and LEAD_TRIG so we see the landscape. Real outcomes
(redeem) -> trustworthy; this is the real test of whether cap-0.70 has a durable edge over more windows than
our 30 live trades."""
import json,os
from collections import defaultdict
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F=os.path.join(ROOT,"data","alltrader_fills_real.json")
fills=json.load(open(F))
print("数据: %d 笔真实成交, %d 窗 (真价x真赎回, 跨数天)\n"%(len(fills),len(set(f['slug'] for f in fills))))
def backtest(lead_trig,max_off,cap):
    bywin=defaultdict(list)
    for f in fills:
        if f["lead"]>=lead_trig and f["off"]<=max_off and f["price"]<cap:
            bywin[f["slug"]].append(f)
    picks=[]
    for slug,fs in bywin.items():
        fs.sort(key=lambda x:x["off"]); picks.append(fs[0])  # earliest qualifying fill
    if not picks: return None
    n=len(picks); w=sum(1 for p in picks if p["won"])
    ev=sum((1-p["price"]) if p["won"] else -p["price"] for p in picks)/n
    pnl=ev*5*n; avgp=sum(p["price"] for p in picks)/n
    return n,w/n*100,avgp,ev,pnl
print("=== 当前filter回测: lead>=8, off<=180, ask<0.70 ===")
r=backtest(8,180,0.70)
if r: print("  n=%d 胜%.0f%% 均价%.3f 净EV/股%+.3f 总PnL(5股/窗)$%+.1f"%r)
print("\n=== PRICE_CAP 敏感性 (lead>=8, off<=180) ===")
print("%-8s %5s %5s %7s %9s %9s"%("cap","n","胜%","均价","净EV/股","总PnL$"))
for cap in (0.60,0.65,0.70,0.75,0.80,0.85):
    r=backtest(8,180,cap)
    if r: print("<%.2f    %5d %4.0f%% %6.3f %+8.3f %+8.1f"%(cap,r[0],r[1],r[2],r[3],r[4]))
print("\n=== LEAD_TRIG 敏感性 (off<=180, cap<0.70) ===")
print("%-8s %5s %5s %7s %9s %9s"%("lead>=","n","胜%","均价","净EV/股","总PnL$"))
for lt in (5,6,8,10,12):
    r=backtest(lt,180,0.70)
    if r: print(">=%-5d  %5d %4.0f%% %6.3f %+8.3f %+8.1f"%(lt,r[0],r[1],r[2],r[3],r[4]))
print("\n注: 全市场真实成交价x真实赎回结算(可信, 非binance重建; 跨数天). 每窗取最早合格fill, 持到结算.")
print("看当前filter(cap0.70)净EV/股是否稳定正, 还是又是小样本/某档侥幸.")
