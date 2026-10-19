"""bt_eebde_conviction.py — eebde bets BOTH sides (two-sided accumulator, value-weights the favorite). So 'net
opposite' may be a 51/49 incidental lean, NOT conviction against us. Re-test by CONVICTION STRENGTH: classify
our fill by what FRACTION of eebde's window $ is on our OPPOSITE side, and by his absolute size. If our win%
degrades MONOTONICALLY as he's MORE heavily against us -> real informed-counterparty signal. If flat across
skew -> the 'opposite' bucket was just two-sided noise (user's hypothesis). Saves eebde slugdir for reuse."""
import httpx, time, json, os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EE="0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
CACHE=os.path.join(ROOT,"data","eebde_slugdir.json")
if os.path.exists(CACHE) and time.time()-os.path.getmtime(CACHE)<7200:
    slugdir=json.load(open(CACHE)); print(f"reused cache: {len(slugdir)} slugs",flush=True)
else:
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
            d=slugdir.setdefault(s,{"Up":0.0,"Down":0.0}); d[x.get("outcome","Up")]=d.get(x.get("outcome","Up"),0)+usd
        pages+=1
        if pages%40==0: print(f"  ...{pages}p {len(slugdir)} slugs",flush=True)
        stalls=stalls+1 if new==0 else 0
        if stalls>3: break
        end=mn-1
    json.dump(slugdir,open(CACHE,"w")); print(f"fetched+saved: {len(slugdir)} slugs",flush=True)
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
    if not d: continue
    tot=d["Up"]+d["Down"]
    if tot<=0: continue
    against=d["Down"] if o["side"]=="Up" else d["Up"]
    skew_against=against/tot   # fraction of his $ on OUR opposite side
    rows.append({**o,"skew":skew_against,"tot":tot})
def rep(s,lab):
    if not s: print(f"  {lab:26s} n=0"); return
    w=sum(1 for r in s if r["won"]); p=sum(r["pnl"] for r in s); sk=sum(r["skew"] for r in s)/len(s)
    print(f"  {lab:26s} n={len(s):4d} win%={w/len(s)*100:5.1f} PnL=${p:+8.2f} avgSkewAgainst={sk:.2f}")
print(f"\nmatched fills: {len(rows)}")
print("=== by eebde CONVICTION against us (skew = his $ fraction on OUR opposite side) ===")
rep([r for r in rows if r["skew"]<0.30],"heavily FOR us (<0.30)")
rep([r for r in rows if 0.30<=r["skew"]<0.45],"lean FOR (0.30-0.45)")
rep([r for r in rows if 0.45<=r["skew"]<0.55],"two-sided/balanced (0.45-0.55)")
rep([r for r in rows if 0.55<=r["skew"]<0.70],"lean AGAINST (0.55-0.70)")
rep([r for r in rows if r["skew"]>=0.70],"heavily AGAINST (>=0.70)")
print("\n=== how two-sided is the 'opposite' bucket really? ===")
opp=[r for r in rows if r["skew"]>0.5]
if opp:
    sk=sorted(r["skew"] for r in opp)
    print(f"  windows where he's net-against: {len(opp)}, median skew-against={sk[len(sk)//2]:.2f} (0.5=coinflip two-sided, 1.0=all against)")
    print(f"  of those, truly heavy (>=0.70): {sum(1 for r in opp if r['skew']>=0.70)}  vs barely (0.5-0.6): {sum(1 for r in opp if r['skew']<0.6)}")
print("\nREAD: real signal iff win% DROPS monotonically as skew-against rises AND 'heavily against' is clearly")
print("worse than 'lean against'. If heavy~=lean~=balanced -> it's two-sided noise, not conviction (user right).")
