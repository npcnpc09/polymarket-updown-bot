"""Lightweight collector: capture every updown window's token IDs + window times while
the market is still indexed by gamma (it de-indexes within minutes of settle). Appends
to data/updown_tokens.jsonl (dedup by slug). Enables a LARGE-sample offline backtest
later (signal from Coinbase + fills/resolution from CLOB prices-history)."""
import httpx, json, time, os, sys
OUT="data/updown_tokens.jsonl"
COINS=["btc","eth","sol","xrp","doge"]
seen=set()
if os.path.exists(OUT):
    for ln in open(OUT,encoding="utf-8"):
        try: seen.add(json.loads(ln)["slug"])
        except: pass
print(f"collector start, {len(seen)} already logged",flush=True)
while True:
    now=int(time.time()); added=0
    with httpx.Client(timeout=12,headers={"User-Agent":"Mozilla/5.0"}) as c:
        for coin in COINS:
            for mt,du in (("5m",300),("15m",900)):
                base=(now//du)*du
                for st in (base-du,base,base+du):
                    slug=f"{coin}-updown-{mt}-{st}"
                    if slug in seen: continue
                    try:
                        r=c.get("https://gamma-api.polymarket.com/markets",params={"slug":slug}).json()
                        if not r: continue
                        m=r[0]; ids=json.loads(m["clobTokenIds"]); outs=json.loads(m["outcomes"])
                        rec={"slug":slug,"coin":coin,"dur":du,"start":st,"settle":st+du,
                             "up":ids[outs.index("Up")],"dn":ids[outs.index("Down")]}
                        open(OUT,"a",encoding="utf-8").write(json.dumps(rec)+"\n")
                        seen.add(slug); added+=1
                    except: continue
    if added: print(f"[{time.strftime('%H:%M:%S')}] +{added} (total {len(seen)})",flush=True)
    time.sleep(25)
