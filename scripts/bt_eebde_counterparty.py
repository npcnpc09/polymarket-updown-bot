"""bt_eebde_counterparty.py — when eebde (informed whale) bets the OPPOSITE side in OUR window, do we lose more?
Memory [[divergence-he-vs-us]]: he-against-us -> we won only 31%. Re-validate on recent data: fetch eebde's
TRADE buys (updown-5m btc/eth/sol, last ~5d), aggregate per slug his net $ direction (Up vs Down), join to OUR
fills by slug, split our win%/PnL by eebde SAME / OPPOSITE / absent. If OPPOSITE is clearly -EV -> a real
informed-flow filter (the relational edge, not a btc-price feature)."""
import httpx, time, json, os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EE="0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
c=httpx.Client(timeout=25,headers={"User-Agent":"Mozilla/5.0"})
floor=int(time.time())-int(5.5*86400); end=int(time.time()); seen=set(); slugdir={}; stalls=0; pages=0
while end>floor:
    try: a=c.get("https://data-api.polymarket.com/activity",params={"user":EE,"limit":500,"end":end}).json()
    except Exception: time.sleep(1); continue
    if not isinstance(a,list) or not a: break
    new=0; mn=end
    for x in a:
        ts=x.get("timestamp")
        if ts and ts<mn: mn=ts
        h=str(x.get("transactionHash",""))+str(x.get("slug",""))+str(x.get("type"))+str(x.get("price",""))+str(x.get("size",""))
        if h in seen: continue
        seen.add(h); new+=1
        if x.get("type")!="TRADE" or (x.get("side") or "").upper()!="BUY": continue
        s=x.get("slug","")
        if "updown-5m-" not in s or s.split("-")[0] not in ("btc","eth","sol"): continue
        usd=float(x.get("usdcSize") or ((x.get("size") or 0)*(x.get("price") or 0)))
        d=slugdir.setdefault(s,{"Up":0.0,"Down":0.0}); d[x.get("outcome","")]=d.get(x.get("outcome",""),0)+usd
    pages+=1
    if pages%20==0: print(f"  ...{pages}p {len(slugdir)} eebde slugs, to {time.strftime('%m-%d %H:%M',time.gmtime(end))}",flush=True)
    stalls=stalls+1 if new==0 else 0
    if stalls>3: break
    end=mn-1
print(f"eebde updown-5m slugs (5.5d): {len(slugdir)}",flush=True)
# our fills
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
ours=[]
for f,keep in (("data/multi_window_engine_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None),
               ("data/early_taker_probe.jsonl",lambda o:o.get("kind")=="entry" and o.get("won") is not None),
               ("data/multi_window_engine_sol_live.jsonl",lambda o:o.get("filled") is True and o.get("won") is not None)):
    for o in (json.loads(l) for l in open(ROOT+"/"+f,encoding="utf-8") if l.strip()):
        if keep(o):
            s=o.get("slug","")
            if "updown-5m-" in s: ours.append({"slug":s,"side":o.get("side"),"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0)})
rows=[]
for o in ours:
    d=slugdir.get(o["slug"])
    if not d: cat="absent"
    else:
        he="Up" if d["Up"]>=d["Down"] else "Down"
        cat="same" if he==o["side"] else "opposite"
    rows.append({**o,"cat":cat})
def rep(s,lab):
    if not s: print(f"  {lab:22s} n=0"); return
    w=sum(1 for r in s if r["won"]); p=sum(r["pnl"] for r in s)
    print(f"  {lab:22s} n={len(s):4d} win%={w/len(s)*100:5.1f} PnL=${p:+8.2f}")
matched=[r for r in rows if r["cat"]!="absent"]
print(f"\nour 5m fills: {len(rows)}, matched to an eebde window: {len(matched)}")
rep(rows,"ALL our fills")
rep([r for r in rows if r["cat"]=="same"],"eebde SAME side")
rep([r for r in rows if r["cat"]=="opposite"],"eebde OPPOSITE side")
rep([r for r in rows if r["cat"]=="absent"],"eebde absent")
print("\nREAD: if 'eebde OPPOSITE' has clearly lower win% (memory said ~31%) -> a real informed-flow filter:")
print("when the whale is against us, skip/downsize. This is the relational edge that could widen the 2pp margin.")
