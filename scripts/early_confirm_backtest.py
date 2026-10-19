"""'Early but more accurate' backtest. Reconstruct the intra-window binance lead PATH at 1-SECOND
granularity. For each 5m window: find when |lead| first crosses 8 (CROSS entry = current early-taker), and
test whether REQUIRING the lead to still be >=8 (same side) CONFIRM_SEC later filters out the false spikes.
Compare win rates: cross-entry vs confirmed-entry vs the cross-but-failed-confirmation (spike) bucket. No PM
price needed for the win-rate question (binance lead path + actual outcome only)."""
import httpx,math,time,statistics
c=httpx.Client(timeout=20,headers={"User-Agent":"Mozilla/5.0"})
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}
TRIG=8.0; MAXOFF=180; CONFIRMS=[10,15,20,30]
now=int(time.time())
windows=[]
for coin,sym in COINS.items():
    base=(now//300)*300
    for k in range(1,45):  # last ~3.7h of settled 5m windows
        st=base-k*300
        if st+300<now-20: windows.append((coin,sym,st))
def klines_1s(sym,st):
    out={}
    r=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1s","startTime":st*1000,"endTime":(st+300)*1000,"limit":1000}).json()
    if not isinstance(r,list): return out
    for x in r: out[int(x[0]//1000)-st]=float(x[4])  # offset_sec -> close
    return out
rows=[]
for coin,sym,st in windows:
    px=klines_1s(sym,st)
    if len(px)<200: continue
    op=px.get(0) or px[min(px)]
    cl=px.get(299) or px.get(max(k for k in px if k<=300))
    if not op or not cl: continue
    winner="Up" if cl>=op else "Down"
    lead={t:math.log(p/op)*1e4 for t,p in px.items()}
    cross=None
    for t in sorted(lead):
        if t>MAXOFF: break
        if abs(lead[t])>=TRIG: cross=t; break
    if cross is None: continue
    cside="Up" if lead[cross]>=0 else "Down"
    rec={"coin":coin,"st":st,"cross_off":cross,"cside":cside,"cross_lead":abs(lead[cross]),"winner":winner,"cwin":cside==winner}
    for cs in CONFIRMS:
        t2=cross+cs
        ok=(t2 in lead and abs(lead[t2])>=TRIG and (lead[t2]>=0)==(cside=="Up"))
        rec["conf%d"%cs]=ok
        rec["conf%d_lead"%cs]=abs(lead[t2]) if t2 in lead else None
    rows.append(rec)
print("可分析窗口: %d (lead在%ds内过%g)\n"%(len(rows),MAXOFF,TRIG))
def wr(rs): return (sum(1 for r in rs if r["cwin"])/len(rs)*100) if rs else 0
print("=== 基准: lead刚过8就进 (现在的做法) ===")
print("  全部 n=%d 胜%.0f%% 均cross_lead%.1f 均cross时点%.0fs"%(len(rows),wr(rows),statistics.mean(r["cross_lead"] for r in rows),statistics.mean(r["cross_off"] for r in rows)))
print("\n=== '早得更准': 过8后等N秒, lead仍>=8同向才进 ===")
print("  %-8s 确认通过(进场) | 确认失败(spike,跳过) | 通过率"%"")
for cs in CONFIRMS:
    passed=[r for r in rows if r["conf%d"%cs]]; failed=[r for r in rows if not r["conf%d"%cs]]
    growth=statistics.mean([r["conf%d_lead"%cs]-r["cross_lead"] for r in passed if r["conf%d_lead"%cs] is not None]) if passed else 0
    print("  等%2ds:  进场n=%-3d 胜%.0f%% | 跳过n=%-3d 胜%.0f%% | 留下%.0f%% (进场lead长了%.1f→更贵)"%(
        cs,len(passed),wr(passed),len(failed),wr(failed),len(passed)/len(rows)*100,growth))
print("\n=== 解读 ===")
best=max(CONFIRMS,key=lambda cs: wr([r for r in rows if r["conf%d"%cs]]))
p=[r for r in rows if r["conf%d"%best]]; f=[r for r in rows if not r["conf%d"%best]]
print("  基准胜%.0f%% → 等%ds确认后进场胜%.0f%% (跳过的spike胜%.0f%%)"%(wr(rows),best,wr(p),wr(f)))
print("  若跳过的spike胜率明显<基准 → '等确认'有效(把假突破筛掉); 若≈基准 → 没用(只是少做单)")
