"""Pull eebde's FULL history via /activity end-cursor (bypass offset cap). TRADE + REDEEM (real settlement).
-> data/eebde_full.jsonl. Same method that worked for ce25."""
import httpx,time,datetime,json,os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EE="0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
c=httpx.Client(timeout=30,headers={"User-Agent":"Mozilla/5.0"})
# leaderboard real profit first
try:
    lb=c.get("https://lb-api.polymarket.com/profit",params={"address":EE,"window":"all"}).json()
    if isinstance(lb,list) and lb: print("eebde 链上真实总盈利: $%+.0f"%lb[0].get("amount",0))
except Exception as e: print("lb err",repr(e)[:50])
DAYS=7; floor=int(time.time())-86400*DAYS
end=int(time.time()); seen=set(); rows=[]; stalls=0
while end>floor:
    try: a=c.get("https://data-api.polymarket.com/activity",params={"user":EE,"limit":500,"end":end}).json()
    except Exception as e: print("err",repr(e)[:40]); time.sleep(1); continue
    if not isinstance(a,list) or not a: break
    new=0; mn=end
    for x in a:
        ts=x.get("timestamp"); h=str(x.get("transactionHash",""))+str(x.get("slug",""))+str(x.get("type"))+str(x.get("price",""))+str(x.get("size",""))
        if ts and ts<mn: mn=ts
        if h in seen: continue
        seen.add(h); rows.append(x); new+=1
    if new==0:
        stalls+=1
        if stalls>3: break
    else: stalls=0
    end=mn-1
    if len(rows)%4000<500 and rows: print("  ...%d条, 到 %s"%(len(rows),datetime.datetime.utcfromtimestamp(end).strftime("%m-%d %H:%M")))
trades=[r for r in rows if r.get("type")=="TRADE"]; redeems=[r for r in rows if r.get("type")=="REDEEM"]
ts=[r.get("timestamp") for r in rows if r.get("timestamp")]
print("\n总 %d | TRADE %d | REDEEM %d"%(len(rows),len(trades),len(redeems)))
if ts: print("跨度 %s ~ %s (%.1f天)"%(datetime.datetime.utcfromtimestamp(min(ts)).strftime("%m-%d %H:%M"),datetime.datetime.utcfromtimestamp(max(ts)).strftime("%m-%d %H:%M"),(max(ts)-min(ts))/86400))
open(os.path.join(ROOT,"data","eebde_full.jsonl"),"w",encoding="utf-8").write("\n".join(json.dumps(r) for r in rows))
print("已存 data/eebde_full.jsonl")
