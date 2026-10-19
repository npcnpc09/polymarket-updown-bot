"""strategy_real_6e1d.py — REAL-MONEY executor for the validated 6e1d favorite model.

Buys favorites where model fair - ask > MARGIN, taker (marketable limit, price-capped),
holds to auto-redeem. Hard risk caps. DRY-RUN by default; pass --live to place orders.

Strategy/model = memory/strategy_6e1d_btc_model_edge.md (validated: 332 endorsements
97% WR / +23% paper, my 8 paper orders 8/8). Guardrails agreed with user.
"""
import argparse, json, os, sys, time, math, re
from datetime import datetime, timezone
import httpx

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE=os.path.join(ROOT,"data","real_6e1d_state.json")
LOG=os.path.join(ROOT,"data","real_6e1d.log")
ADDR_6E1D="0x6e1d5040d0ac73709b0621f620d2a60b80d2d0fa"
SIGMA_ANN=0.16; SIGMA_MIN=SIGMA_ANN/math.sqrt(525600.0)

# ---- risk caps (hard) ----
BANKROLL=50.0; SIZE=5.0; PER_MKT=10.0; MAX_OPEN=10
MARGIN=0.06            # real entry margin (>paper 0.04 to absorb slippage)
MAX_TTX_H=48; MIN_TTX_H=0.1   # prefer markets resolving within 48h
COOLDOWN=90           # per-market cooldown (s) -> idempotency vs double-order

def iso(): return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
def log(m):
    line=f"[{iso()}] {m}"; print(line,flush=True)
    try: open(LOG,"a",encoding="utf-8").write(line+"\n")
    except: pass
def Phi(x): return 0.5*(1+math.erf(x/math.sqrt(2)))
def parse_iso(s):
    try: return datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()
    except: return None
def load_env():
    f=os.path.join(ROOT,".env")
    if os.path.exists(f):
        for l in open(f,encoding="utf-8"):
            if "=" in l and not l.startswith("#"):
                k,v=l.strip().split("=",1); os.environ.setdefault(k.strip(),v.strip())
    return os.environ.get("POLY_PK"),os.environ.get("POLY_PROXY")

def parse_market(q):
    s=(q or "").lower().replace(",","")
    nums=[]
    for m in re.finditer(r"\$?\s*(\d+(?:\.\d+)?)\s*(k)?",s):
        v=float(m.group(1))*(1000 if m.group(2) else 1)
        if 1000<=v<=1000000: nums.append(v)
    if "between" in s and len(nums)>=2: return ("range",sorted(nums[:2]))
    if "up or down" in s: return ("updown",[])
    if ("reach" in s or "hit" in s) and nums: return ("touch_above",[nums[0]])
    if "dip" in s and nums: return ("touch_below",[nums[0]])
    if ("above" in s or "at least" in s or "more than" in s) and nums: return ("above",[nums[0]])
    if ("below" in s or "under" in s) and nums: return ("below",[nums[0]])
    return (None,None)

def model_p_yes(mt,strikes,S,tau_min,open_px=None):
    if tau_min<=0 or S<=0: return None
    v=SIGMA_MIN*math.sqrt(tau_min)
    def pa(K): return Phi(math.log(S/K)/v)
    if mt=="above": return pa(strikes[0])
    if mt=="below": return 1-pa(strikes[0])
    if mt=="range": return pa(strikes[0])-pa(strikes[1])
    if mt=="touch_above":
        K=strikes[0]; return 1.0 if S>=K else min(1.0,2*(1-Phi(math.log(K/S)/v)))
    if mt=="touch_below":
        K=strikes[0]; return 1.0 if S<=K else min(1.0,2*Phi(-math.log(S/K)/v))
    if mt=="updown": return pa(open_px if open_px else S)
    return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--live",action="store_true",help="actually place orders (default dry-run)")
    ap.add_argument("--interval",type=int,default=20)
    ap.add_argument("--once",action="store_true",help="single cycle then exit (for dry-run check)")
    ap.add_argument("--size",type=float,default=SIZE,help="$/order (>=1.2; use small for first real fill test)")
    ap.add_argument("--bankroll",type=float,default=BANKROLL,help="max total $ deployed (hard cap)")
    ap.add_argument("--allow-touch",action="store_true",help="include reach/dip touch markets (model less reliable there)")
    a=ap.parse_args()
    pk,proxy=load_env()
    if not pk or not proxy: log("MISSING creds"); sys.exit(1)
    from polymarket import SecureClient
    cli=SecureClient.create(private_key=pk,wallet=proxy)
    http=httpx.Client(timeout=15,headers={"User-Agent":"Mozilla/5.0"})
    mode="LIVE" if a.live else "DRY-RUN"
    bal=float(cli.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6
    log(f"=== strategy_real_6e1d [{mode}] wallet ${bal:.2f} | cap ${a.bankroll} size ${a.size} "
        f"per_mkt ${PER_MKT} max_open {MAX_OPEN} margin {MARGIN} ===")

    st=json.load(open(STATE)) if os.path.exists(STATE) else {"open":{},"closed":[],"spent":0.0}
    omcache={}; _opencache={}; _recent={}   # _recent: cid -> last-order ts (idempotency)

    # (4) rate-limit backoff wrapper for REST polling
    def http_get(url, **kw):
        d=1
        for _ in range(5):
            try:
                r=http.get(url, **kw)
                if r.status_code==429:
                    log(f"  429 backoff {d}s"); time.sleep(d); d=min(d*2,16); continue
                return r.json()
            except Exception:
                time.sleep(d); d=min(d*2,16)
        return None

    # (3) balance read with 0-guard (SDK intermittently returns 0)
    def safe_balance(committed):
        for _ in range(3):
            try:
                b=float(cli.get_balance_allowance(asset_type="COLLATERAL").balance)/1e6
                if b==0 and committed>0.01:
                    log("  balance read 0 w/ open positions -> transient, retry"); time.sleep(1.0); continue
                return b
            except Exception: time.sleep(1.0)
        return None

    def live_spot(sym):
        d=http_get("https://api.binance.com/api/v3/ticker/price",params={"symbol":sym})
        try: return float(d["price"]) if d else None
        except: return None
    def updown_open(endts,sym):
        k=int(endts-86400)
        ck=(sym,k)
        if ck in _opencache: return _opencache[ck]
        o=None
        kl=http_get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1m","startTime":int(k*1000),"endTime":int((k+120)*1000),"limit":2})
        if kl:
            try: o=float(kl[0][1])
            except: pass
        _opencache[ck]=o; return o
    def market_meta(cid):
        if cid in omcache: return omcache[cid]
        info=None
        try:
            d=http_get("https://gamma-api.polymarket.com/markets",params={"condition_ids":cid})
            m=d[0] if isinstance(d,list) and d else None
            if m:
                mt,strikes=parse_market(m.get("question",""))
                toks=json.loads(m.get("clobTokenIds","[]")); outs=json.loads(m.get("outcomes","[]"))
                end=parse_iso(m.get("endDate"))
                if mt and len(toks)>=2 and end and not m.get("closed"):
                    q=m.get("question","").lower()
                    asset="BTC" if "bitcoin" in q else "ETH" if "ethereum" in q else None
                    if asset:
                        info=dict(cid=cid,q=m.get("question",""),mt=mt,strikes=strikes,end=end,
                                  toks=toks,outs=outs if len(outs)>=2 else ["Yes","No"],
                                  sym="BTCUSDT" if asset=="BTC" else "ETHUSDT")
        except: pass
        omcache[cid]=info; return info
    def best_ask(tok):
        try:
            ob=cli.get_order_book(token_id=tok)
            a=min((float(l.price) for l in ob.asks),default=None); return a
        except: return None

    def cycle():
        nonlocal st
        committed=sum(p["cost"] for p in st["open"].values())
        bal=safe_balance(committed)
        if bal is None: log("  balance unavailable -> skip cycle"); return   # (3)
        room=min(bal,a.bankroll)-committed
        open_n=len(st["open"])
        log(f"  balance ${bal:.2f} | open {open_n} committed ${committed:.2f} | room ${room:.2f}")
        if room<a.size-0.01 or open_n>=MAX_OPEN:
            log(f"  no room (need ${a.size}, max_open {MAX_OPEN}) -> hold"); return
        # universe = his recent BTC/ETH markets
        acts=http_get("https://data-api.polymarket.com/activity",params={"user":ADDR_6E1D,"limit":200}) or []
        cids=[]
        for x in acts:
            if x.get("type")=="TRADE" and x.get("side")=="BUY":
                q=(x.get("title","") or "").lower()
                if "bitcoin" in q or "btc" in q or "ethereum" in q:
                    if x["conditionId"] not in cids: cids.append(x["conditionId"])
        now=time.time(); cand=[]
        for cid in cids:
            m=market_meta(cid)
            if not m: continue
            if cid in st["open"] and st["open"][cid]["cost"]>=PER_MKT-0.01: continue
            if now-_recent.get(cid,0)<COOLDOWN: continue   # (1) idempotency: no re-order within cooldown
            if m["mt"] in ("touch_above","touch_below") and not a.allow_touch: continue  # model least reliable on touch
            ttx_h=(m["end"]-now)/3600
            if not (MIN_TTX_H<=ttx_h<=MAX_TTX_H): continue
            S=live_spot(m["sym"]);
            if not S: continue
            opx=updown_open(m["end"],m["sym"]) if m["mt"]=="updown" else None
            p=model_p_yes(m["mt"],m["strikes"],S,(m["end"]-now)/60.0,opx)
            if p is None: continue
            for side,token,fair in (("Yes" if m["outs"][0] in("Yes","Up") else m["outs"][0],m["toks"][0],p),
                                    (m["outs"][1],m["toks"][1],1-p)):
                ask=best_ask(token)
                if ask is None: continue
                edge=fair-ask
                if edge>MARGIN and ask<0.985:
                    cand.append((edge,cid,m,side,token,ask,fair,ttx_h))
        cand.sort(reverse=True)
        if not cand: log("  no +edge candidate this cycle"); return
        edge,cid,m,side,token,ask,fair,ttx_h=cand[0]
        # price-capped marketable limit
        cap=min(round(ask+0.02,2),round(fair-0.02,2))
        if cap<ask: log(f"  best cand edge ok but cap<ask, skip"); return
        shares=max(1.0,round(a.size/ask))
        while shares*cap<1.01: shares+=1.0   # ensure >= $1 marketable minimum
        log(f"  >>> BUY {side} '{m['q'][:44]}' ask={ask:.3f} fair={fair:.3f} edge=+{edge:.3f} "
            f"ttx={ttx_h:.1f}h ~{shares:.0f}sh@<= {cap} (~${shares*cap:.2f})")
        _recent[cid]=time.time()   # (1) mark BEFORE placing -> no double-order even if order is slow/fails
        if not a.live:
            log("      [DRY-RUN] would place; not trading"); return
        try:
            signed=cli.create_limit_order(token_id=token,price=cap,size=shares,side="BUY",post_only=False)
            r=cli.post_order(signed)
            if getattr(r,"ok",False):
                mk=getattr(r,"making_amount",None); tk=getattr(r,"taking_amount",None)
                got=float(tk) if tk else shares
                # conservative cost: max(reported making, shares*cap) -> never under-count slippage
                cost=max(float(mk) if mk else 0.0, got*cap)
                fill_px=cost/got if got>0 else None
                # (2) fill-price precision / slippage guard
                if fill_px is not None and fill_px>cap+0.005:
                    log(f"      WARN fill_px {fill_px:.4f} > cap {cap} (precision drift/slippage)")
                pos=st["open"].get(cid,{"q":m["q"],"side":side,"cost":0.0,"shares":0.0,"toks":m["toks"],"outs":m["outs"],"end":m["end"]})
                pos["cost"]+=cost; pos["shares"]+=got
                st["open"][cid]=pos; st["spent"]=st.get("spent",0)+cost
                json.dump(st,open(STATE,"w"))
                log(f"      FILLED {got:.2f}sh cost ${cost:.2f} fill_px={fill_px} raw(mk={mk},tk={tk}) oid={getattr(r,'order_id','')[:12]}")
            else:
                log(f"      REJECTED status={getattr(r,'status','?')} err={getattr(r,'error_msg',None)}")
        except Exception as e:
            log(f"      order exc {str(e)[:90]}")

    # settle check: mark resolved positions (auto-redeem handles cash)
    def settle():
        nonlocal st
        for cid in list(st["open"].keys()):
            pos=st["open"][cid]
            try:
                d=http_get("https://gamma-api.polymarket.com/markets",params=[("closed","true"),("condition_ids",cid)])
                d2=http_get("https://gamma-api.polymarket.com/markets",params=[("condition_ids",cid)])
                m=(d[0] if isinstance(d,list) and d else (d2[0] if isinstance(d2,list) and d2 else None))
                if not m: continue
                op=[float(x) for x in json.loads(m.get("outcomePrices","[]"))]
                if not op or max(op)<0.99: continue
                idx=pos["outs"].index(pos["side"]) if pos["side"] in pos["outs"] else (0 if pos["side"]=="Yes" else 1)
                win=op[idx]>0.99
                payout=pos["shares"]*1.0 if win else 0.0
                pnl=payout-pos["cost"]
                st["closed"].append({"cid":cid,"q":pos["q"],"side":pos["side"],"cost":round(pos["cost"],2),"win":win,"pnl":round(pnl,2)})
                del st["open"][cid]; json.dump(st,open(STATE,"w"))
                log(f"  SETTLED {'WIN' if win else 'LOSS'} {pos['side']} '{pos['q'][:40]}' pnl ${pnl:+.2f}")
            except: pass

    while True:
        try: settle(); cycle()
        except Exception as e: log(f"cycle exc {str(e)[:80]}")
        # report
        c=st["closed"];
        if c:
            w=sum(1 for x in c if x["win"]); pnl=sum(x["pnl"] for x in c)
            log(f"  REALIZED: {len(c)} closed, {w}W {len(c)-w}L, PnL ${pnl:+.2f}")
        if a.once: break
        time.sleep(a.interval)

if __name__=="__main__": main()
