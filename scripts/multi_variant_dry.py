"""multi_variant_dry.py — evolve the continuous-averaging strategy in DRY by running MANY param variants in
ONE process on SHARED data (1 set of binance/book polls). Every variant sees IDENTICAL windows -> OOS-fair,
no overfit-from-refitting. CPU/storage ~ one bot regardless of variant count. Per window: poll lead + both
asks once; each variant applies its own base/add/wobble logic; at settle record each variant's outcome.
Output: data/mv_dry.jsonl (one row per variant per settled window). Analyze with analyze_mv.py."""
import asyncio, json, time, signal, sys, os, math, datetime
import httpx
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding="utf-8",errors="replace")
    except: pass
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COINS={"btc":"BTCUSDT","eth":"ETHUSDT","sol":"SOLUSDT","xrp":"XRPUSDT","doge":"DOGEUSDT"}; GAMMA="https://gamma-api.polymarket.com/markets"
OFF_BASE=(15,70); ADD_CHECKS=[90,150,210]
# --- VARIANTS: grid over lead_base / sizing / lead_add / retrace / max_adds / price_cap ---
VARIANTS=[
 {"n":"A_base",        "lb":5,"bs":5,"as_":5,"la":8, "rt":3,"ma":3,"cap":0.92},
 {"n":"B_valweight",   "lb":5,"bs":2,"as_":10,"la":8,"rt":3,"ma":3,"cap":0.92},  # small base big adds
 {"n":"C_tightbase",   "lb":8,"bs":5,"as_":5,"la":8, "rt":3,"ma":3,"cap":0.92},  # higher base gate
 {"n":"D_looseRetrace","lb":5,"bs":5,"as_":5,"la":8, "rt":5,"ma":3,"cap":0.92},  # tolerate dips
 {"n":"E_tightRetrace","lb":5,"bs":5,"as_":5,"la":8, "rt":2,"ma":3,"cap":0.92},
 {"n":"F_moreAdds",    "lb":5,"bs":3,"as_":6,"la":8, "rt":3,"ma":5,"cap":0.92},
 {"n":"G_cheapCap",    "lb":5,"bs":5,"as_":5,"la":8, "rt":3,"ma":3,"cap":0.85},  # only buy <0.85
 {"n":"H_strongAdd",   "lb":5,"bs":3,"as_":8,"la":12,"rt":3,"ma":3,"cap":0.92},  # add only on strong strengthen
 {"n":"I_valTight",    "lb":8,"bs":2,"as_":10,"la":10,"rt":3,"ma":3,"cap":0.90}, # tight base + valweight
 {"n":"J_lateBase",    "lb":8,"bs":3,"as_":7,"la":10,"rt":4,"ma":4,"cap":0.92},
]
OUTF=os.path.join(ROOT,"data","mv_dry.jsonl"); LOG=os.path.join(ROOT,"data","mv_dry.log")
_run=True
def _sig(*_):
    global _run; _run=False
signal.signal(signal.SIGINT,_sig)
def now(): return time.time()
def log(m):
    line=f"[{datetime.datetime.utcnow().strftime('%H:%M:%S')}] {m}"; print(line,flush=True)
    try: open(LOG,"a",encoding="utf-8").write(line+"\n")
    except: pass
async def bpx(c,sym):
    try: return float((await c.get("https://api.binance.com/api/v3/ticker/price",params={"symbol":sym},timeout=8)).json()["price"])
    except: return None
async def kopen(c,sym,st):
    try: return float((await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":st*1000,"limit":1},timeout=8)).json()[0][1])
    except: return None
async def toks(c,slug):
    try:
        a=(await c.get(GAMMA,params={"slug":slug},timeout=10)).json()
        if a: ids=json.loads(a[0]["clobTokenIds"]); outs=json.loads(a[0]["outcomes"]); return ids[outs.index("Up")],ids[outs.index("Down")]
    except: pass
    return None,None
async def topask(c,tok):
    try:
        b=(await c.get("https://clob.polymarket.com/book",params={"token_id":tok},timeout=8)).json()
        asks=sorted(float(a["price"]) for a in b.get("asks",[]) if float(a["size"])>0 and 0<float(a["price"])<1)
        return asks[0] if asks else None
    except: return None
async def kwin(c,sym,st,wa=240):
    try:
        k1=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":st*1000,"limit":1},timeout=8)).json()
        k2=(await c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":(st+wa)*1000,"limit":1},timeout=8)).json()
        return "Up" if float(k2[0][4])>=float(k1[0][1]) else "Down"
    except: return None
def new_state(): return {"side":None,"lb":None,"peak":None,"fills":[],"adds":set(),"wobble":False}
async def main():
    W={}
    async with httpx.AsyncClient() as c:
        log(f"multi_variant_dry START [DRY] {len(VARIANTS)} variants, shared data")
        while _run:
            t=now()
            for coin,sym in COINS.items():
                ws=int(t//300)*300; slug=f"{coin}-updown-5m-{ws}"
                if slug not in W:
                    up,dn=await toks(c,slug)
                    if up: W[slug]={"coin":coin,"sym":sym,"st":ws,"up":up,"dn":dn,"open":await kopen(c,sym,ws),"settled":False,"V":{v["n"]:new_state() for v in VARIANTS}}
            for slug,w in list(W.items()):
                sec=t-w["st"]
                if w["open"] is None: w["open"]=await kopen(c,w["sym"],w["st"]); continue
                if sec<=max(ADD_CHECKS)+12 and not w["settled"]:
                    px=await bpx(c,w["sym"])
                    if px:
                        lead=math.log(px/w["open"])*1e4
                        # fetch both asks once (shared)
                        aU=await topask(c,w["up"]); aD=await topask(c,w["dn"])
                        for v in VARIANTS:
                            st_=w["V"][v["n"]]
                            # BASE
                            if st_["side"] is None and OFF_BASE[0]<=sec<=OFF_BASE[1] and abs(lead)>=v["lb"]:
                                side="Up" if lead>=0 else "Down"; ask=aU if side=="Up" else aD
                                if ask and ask<v["cap"]:
                                    st_["side"]=side; st_["lb"]=abs(lead); st_["peak"]=abs(lead); st_["fills"].append((ask,v["bs"]))
                            # ADDS
                            elif st_["side"] and not st_["wobble"] and len(st_["adds"])<v["ma"]:
                                lt=lead*(1 if st_["side"]=="Up" else -1)
                                if lt>st_["peak"]: st_["peak"]=lt
                                if st_["peak"]-lt>v["rt"]: st_["wobble"]=True
                                else:
                                    for ck in ADD_CHECKS:
                                        if ck in st_["adds"] or sec<ck or sec>ck+15: continue
                                        if lt>=v["la"] and lt>=st_["lb"]:
                                            ask=aU if st_["side"]=="Up" else aD
                                            if ask and ask<v["cap"]: st_["adds"].add(ck); st_["fills"].append((ask,v["as_"]))
                                        break
                # SETTLE
                if sec>308 and not w["settled"]:
                    w["settled"]=True
                    win=await kwin(c,w["sym"],w["st"])
                    for v in VARIANTS:
                        st_=w["V"][v["n"]]
                        if not st_["fills"]: continue
                        won=(st_["side"]==win) if win else None
                        if won is None: continue
                        sh=sum(s for _,s in st_["fills"]); cost=sum(p*s for p,s in st_["fills"]); avg=cost/sh
                        pnl=(sh-cost) if won else -cost
                        open(OUTF,"a",encoding="utf-8").write(json.dumps({"v":v["n"],"coin":w["coin"],"slug":slug,"won":won,"n_fills":len(st_["fills"]),"shares":sh,"avg_px":round(avg,3),"pnl":round(pnl,2),"wobble":st_["wobble"]})+"\n")
                    nset=sum(1 for v in VARIANTS if w["V"][v["n"]]["fills"])
                    log(f"SETTLE {slug} win={win} ({nset} variants traded)")
                    del W[slug]
            await asyncio.sleep(4)
if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
