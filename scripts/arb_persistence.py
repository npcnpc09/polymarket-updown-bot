"""arb_persistence.py — Measure how long REAL arbs actually persist (no WS sync artifacts).

Critique addressed: the earlier "arbs last 3ms" came from WS delta reconstruction where
Up/Down update at slightly different times -> a phantom momentary sum<1. That's an
artifact, not a real tradeable arb. If real arbs only lasted 3ms, nobody could ever
arb -- yet many do. So: measure properly.

Method: poll the REST order book (each snapshot internally consistent) for both legs of
several markets, back-to-back, every ~400ms. Compute the REAL takeable arb: walk N shares
on each leg, sum of avg prices. sum<1 = real arb at that snapshot. Track PERSISTENCE:
how many consecutive snapshots an arb stays open -> real duration. Require >=2 consecutive
snapshots to count (filters single-snapshot flukes).

Output: data/arb_persistence.jsonl + console summary (duration distribution).
"""
import json, time, sys, bisect
from collections import defaultdict
from datetime import datetime, timezone
import httpx

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except: pass

ROOT=__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))
OUTF=ROOT+r"\data\arb_persistence.jsonl"
GAMMA="https://gamma-api.polymarket.com/markets"
BOOK="https://clob.polymarket.com/book"
ASSETS=["btc","eth","sol","xrp"]
N_SHARES=5.0
POLL_SEC=0.4
RUN_SEC=240
ARB_TH=1.00      # sum below this = arb

def now(): return time.time()
def iso(): return datetime.now(timezone.utc).strftime("%H:%M:%S")
def log(m): print(f"[{iso()}] {m}",flush=True)

def walk(asks,n):
    rem=n; cost=0.0
    for p,s in sorted(asks):
        if p>=1.0: break
        take=min(rem,s); cost+=take*p; rem-=take
        if rem<=1e-9: break
    return cost/n if rem<=1e-9 else None

def book_asks(http,tok):
    try:
        b=http.get(BOOK,params={"token_id":tok},timeout=6).json()
        return [(float(a["price"]),float(a["size"])) for a in b.get("asks",[])]
    except: return None

def discover(http):
    tnow=int(now()); mk={}
    for a in ASSETS:
        for mt,du in (("5m",300),("15m",900)):
            st=(tnow//du)*du; slug=f"{a}-updown-{mt}-{st}"
            try:
                arr=http.get(GAMMA,params={"slug":slug},timeout=8).json()
                if arr and not arr[0].get("closed"):
                    ids=json.loads(arr[0]["clobTokenIds"]); outs=json.loads(arr[0]["outcomes"])
                    mk[slug]={"up":ids[outs.index("Up")],"dn":ids[outs.index("Down")],"settle":st+du,"asset":a}
            except: pass
    return mk

def main():
    http=httpx.Client()
    log(f"arb persistence probe | REST poll {POLL_SEC}s, N={N_SHARES}sh, arb if sum<{ARB_TH}")
    mk=discover(http); log(f"tracking {len(mk)} markets: {list(mk)}")
    state=defaultdict(lambda:{"open":False,"start":None,"polls":0,"min_sum":2.0,"min_depth":0})
    episodes=[]; t_end=now()+RUN_SEC; polls=0; last_disc=now()
    while now()<t_end:
        if now()-last_disc>60:
            mk=discover(http); last_disc=now()
        for slug,m in list(mk.items()):
            if m["settle"]-now()<20:  # skip near-settle
                continue
            au=book_asks(http,m["up"]); ad=book_asks(http,m["dn"])
            if au is None or ad is None: continue
            pu=walk(au,N_SHARES); pd=walk(ad,N_SHARES)
            if pu is None or pd is None: continue
            s=pu+pd
            st=state[slug]
            if s<ARB_TH:
                if not st["open"]:
                    st.update(open=True,start=now(),polls=1,min_sum=s)
                else:
                    st["polls"]+=1; st["min_sum"]=min(st["min_sum"],s)
            else:
                if st["open"]:
                    dur=now()-st["start"]
                    ep={"slug":slug,"asset":m["asset"],"dur_ms":round(dur*1000),"polls":st["polls"],"min_sum":round(st["min_sum"],4)}
                    episodes.append(ep)
                    with open(OUTF,"a",encoding="utf-8") as f: f.write(json.dumps(ep)+"\n")
                    if st["polls"]>=2:
                        log(f"  ARB {slug} persisted {ep['dur_ms']}ms ({st['polls']} polls) min_sum={ep['min_sum']}")
                    st.update(open=False,start=None,polls=0,min_sum=2.0)
        polls+=1
        time.sleep(POLL_SEC)
    # close any open
    for slug,st in state.items():
        if st["open"]:
            episodes.append({"slug":slug,"dur_ms":round((now()-st["start"])*1000),"polls":st["polls"],"min_sum":round(st["min_sum"],4)})
    real=[e for e in episodes if e["polls"]>=2]   # multi-poll confirmed = real
    flukes=[e for e in episodes if e["polls"]<2]
    log("="*55)
    log(f"poll cycles={polls} | arb episodes total={len(episodes)} | CONFIRMED(>=2 polls)={len(real)} single-poll-flukes={len(flukes)}")
    if real:
        durs=sorted(e["dur_ms"] for e in real)
        log(f"CONFIRMED arb persistence: min={durs[0]}ms median={durs[len(durs)//2]}ms max={durs[-1]}ms")
        log(f"  persisted >=400ms: {sum(1 for d in durs if d>=400)}  >=1s: {sum(1 for d in durs if d>=1000)}  >=2s: {sum(1 for d in durs if d>=2000)}")
        bya=defaultdict(int)
        for e in real: bya[e.get("asset","?")]+=1
        log(f"  by asset: {dict(bya)}")
        log(f"  -> if many persist >=1s, they ARE capturable at our latency (refutes the 3ms claim)")
    http.close()

if __name__=="__main__": main()
