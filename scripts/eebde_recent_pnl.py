"""eebde_recent_pnl.py — eebde's REAL realized profit, recent windows (leaderboard /profit) + per-day breakdown
from on-chain TRADE/REDEEM (last ~5 days). Realized PnL/day = sum(REDEEM payouts that day) - sum(BUY cost of
trades that day) is approximate (buys & their redeems fall on different days); the leaderboard windows are the
authoritative recent figure."""
import httpx, time, datetime, json
EE="0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
c=httpx.Client(timeout=30,headers={"User-Agent":"Mozilla/5.0"})
print("=== eebde leaderboard realized profit by window ===")
for win in ("1d","7d","30d","all"):
    try:
        r=c.get("https://lb-api.polymarket.com/profit",params={"address":EE,"window":win}).json()
        amt=r[0].get("amount") if isinstance(r,list) and r else (r.get("amount") if isinstance(r,dict) else None)
        print(f"  {win:4s}: ${amt:+,.0f}" if amt is not None else f"  {win:4s}: (no data) {str(r)[:80]}")
    except Exception as e: print(f"  {win:4s}: err {repr(e)[:50]}")
# per-day from activity (last 5 days)
print("\n=== per-day on-chain flow (last ~5d): BUY cost vs REDEEM payout ===")
floor=int(time.time())-86400*5; end=int(time.time()); seen=set(); rows=[]; stalls=0
while end>floor:
    try: a=c.get("https://data-api.polymarket.com/activity",params={"user":EE,"limit":500,"end":end}).json()
    except Exception: time.sleep(1); continue
    if not isinstance(a,list) or not a: break
    new=0; mn=end
    for x in a:
        ts=x.get("timestamp")
        h=str(x.get("transactionHash",""))+str(x.get("slug",""))+str(x.get("type"))+str(x.get("price",""))+str(x.get("size",""))
        if ts and ts<mn: mn=ts
        if h in seen: continue
        seen.add(h); rows.append(x); new+=1
    stalls=stalls+1 if new==0 else 0
    if stalls>3: break
    end=mn-1
byday={}
for x in rows:
    ts=x.get("timestamp")
    if not ts or ts<floor: continue
    d=datetime.datetime.utcfromtimestamp(ts).strftime("%m-%d")
    rec=byday.setdefault(d,{"buy":0.0,"sell":0.0,"redeem":0.0,"nbuy":0,"nred":0})
    typ=x.get("type"); sz=float(x.get("size") or 0); px=float(x.get("price") or 0); usdc=float(x.get("usdcSize") or (sz*px))
    if typ=="TRADE":
        if (x.get("side") or "").upper()=="BUY": rec["buy"]+=usdc; rec["nbuy"]+=1
        else: rec["sell"]+=usdc
    elif typ=="REDEEM": rec["redeem"]+=usdc; rec["nred"]+=1
print(f"  {'day':6s} {'#buy':>5s} {'buy$':>10s} {'sell$':>9s} {'#red':>5s} {'redeem$':>11s} {'net(red+sell-buy)':>17s}")
for d in sorted(byday):
    r=byday[d]; net=r["redeem"]+r["sell"]-r["buy"]
    print(f"  {d:6s} {r['nbuy']:5d} ${r['buy']:9,.0f} ${r['sell']:8,.0f} {r['nred']:5d} ${r['redeem']:10,.0f} ${net:+16,.0f}")
print("\nNOTE: daily net mixes buys with redeems of EARLIER windows (lag), so single-day net is noisy;")
print("the leaderboard 1d/7d windows above are the clean realized figure. Volume (#buy, buy$) shows activity level.")
