"""Pull ce25's FULL history by walking the /activity `end` time-cursor backward (bypasses the offset cap).
Collect TRADE + REDEEM events over the past N days. REDEEMs give REAL outcomes (his winning-side payout =
real settlement), so we can decode on real data, NOT binance reconstruction. Saves to data/ce25_full.jsonl."""
import httpx,time,datetime,json,os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CE="0xcE25E214D5cfE4f459cf67F08DF581885AAE7Fdc"
c=httpx.Client(timeout=30,headers={"User-Agent":"Mozilla/5.0"})
DAYS=7
floor=int(time.time())-86400*DAYS
end=int(time.time()); seen=set(); rows=[]; stalls=0
while end>floor:
    try:
        a=c.get("https://data-api.polymarket.com/activity",params={"user":CE,"limit":500,"end":end}).json()
    except Exception as e:
        print("err",repr(e)[:50]); time.sleep(1); continue
    if not isinstance(a,list) or not a: break
    new=0; mn=end
    for x in a:
        ts=x.get("timestamp"); h=x.get("transactionHash","")+str(x.get("slug",""))+str(x.get("type"))+str(x.get("price",""))+str(x.get("size",""))
        if ts and ts<mn: mn=ts
        if h in seen: continue
        seen.add(h); rows.append(x); new+=1
    if new==0:
        stalls+=1
        if stalls>3: print("连续无新数据, 停"); break
    else: stalls=0
    end=mn-1
    if len(rows)%2000<500 and len(rows)>0:
        print("  ...已拉 %d 条, 到 %s"%(len(rows),datetime.datetime.utcfromtimestamp(end).strftime("%m-%d %H:%M")))
trades=[r for r in rows if r.get("type")=="TRADE"]
redeems=[r for r in rows if r.get("type")=="REDEEM"]
ts=[r.get("timestamp") for r in rows if r.get("timestamp")]
print("\n总拉取 %d 条 | TRADE %d | REDEEM %d"%(len(rows),len(trades),len(redeems)))
if ts:
    print("时间跨度: %s ~ %s (%.1f天)"%(datetime.datetime.utcfromtimestamp(min(ts)).strftime("%m-%d %H:%M"),datetime.datetime.utcfromtimestamp(max(ts)).strftime("%m-%d %H:%M"),(max(ts)-min(ts))/86400))
out=os.path.join(ROOT,"data","ce25_full.jsonl")
with open(out,"w",encoding="utf-8") as f:
    for r in rows: f.write(json.dumps(r)+"\n")
print("已存", out)
# 快速看 redeem 能不能定真实outcome
print("\nREDEEM样例(真实赎回=真实结算):")
for r in redeems[:4]:
    print("  %s redeem usdc=$%.2f size=%.1f"%(r.get("slug"),r.get("usdcSize") or 0,r.get("size") or 0))
