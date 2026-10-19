"""eebde_perday.py — per-day realized PnL for eebde. His updown positions settle within minutes, so daily
net = REDEEM payout + SELL - BUY cost is a good daily PnL. Fetches last N days of activity (paginated by
end-cursor), prints progress unbuffered, writes result to data/eebde_perday.txt."""
import httpx, time, datetime, sys, os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EE="0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
DAYS=4
c=httpx.Client(timeout=20,headers={"User-Agent":"Mozilla/5.0"})
floor=int(time.time())-86400*DAYS; end=int(time.time()); seen=set(); rows=[]; stalls=0; pages=0
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
    pages+=1
    if pages%10==0: print(f"  ...{pages} pages, {len(rows)} events, to {datetime.datetime.utcfromtimestamp(end).strftime('%m-%d %H:%M')}",flush=True)
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
out=[f"=== eebde per-day (last {DAYS}d, {len(rows)} events) ===",
     f"  {'day':6s} {'#buy':>6s} {'buy$':>11s} {'sell$':>10s} {'#red':>6s} {'redeem$':>12s} {'NET$':>12s}"]
for d in sorted(byday):
    r=byday[d]; net=r["redeem"]+r["sell"]-r["buy"]
    out.append(f"  {d:6s} {r['nbuy']:6d} ${r['buy']:10,.0f} ${r['sell']:9,.0f} {r['nred']:6d} ${r['redeem']:11,.0f} ${net:+11,.0f}")
out.append("NOTE: updown settles in minutes so buy & its redeem are same-day -> daily net is a fair PnL proxy.")
txt="\n".join(out)
print("\n"+txt,flush=True)
open(os.path.join(ROOT,"data","eebde_perday.txt"),"w",encoding="utf-8").write(txt)
