"""DRY copy-follow probe for 0x437f (Shanghai-weather trader). NO ORDERS — measurement only.
Polls data-api activity every ~15s; on each NEW trade of his, snapshots the live CLOB book for that
token and records the 'copy tax': (best ask - his fill) for BUYs / (his fill - best bid) for SELLs,
plus available depth and detection latency. Decides copy-trade viability after ~2 days.
-> data/copy437f_dry.jsonl / .log"""
import json, time, os, sys, urllib.request, datetime

W="0x437f1c745a4abd87d5a9a2c61294139d86005b95"
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTF=os.path.join(ROOT,"data","copy437f_dry.jsonl")
LOGF=os.path.join(ROOT,"data","copy437f_dry.log")
POLL=15

def log(m):
    line=f"[{datetime.datetime.utcnow().strftime('%m-%d %H:%M:%S')}] {m}"
    print(line,flush=True)
    try: open(LOGF,"a",encoding="utf-8").write(line+"\n")
    except: pass

def get(url,timeout=15):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req,timeout=timeout).read())

def activity(limit=100):
    return get(f"https://data-api.polymarket.com/activity?user={W}&limit={limit}")

def book(token):
    try:
        b=get(f"https://clob.polymarket.com/book?token_id={token}",timeout=10)
        bids=sorted(((float(x["price"]),float(x["size"])) for x in b.get("bids",[]) if float(x["size"])>0),key=lambda z:z[0])
        asks=sorted(((float(x["price"]),float(x["size"])) for x in b.get("asks",[]) if float(x["size"])>0),key=lambda z:z[0])
        bb=bids[-1] if bids else (None,0.0); ba=asks[0] if asks else (None,0.0)
        return bb[0],bb[1],ba[0],ba[1]
    except Exception as e:
        return None,0.0,None,0.0

def key(r): return f"{r.get('transactionHash','')}_{r.get('asset','')}_{r.get('timestamp','')}_{r.get('side','')}"

def main():
    log(f"copy437f DRY probe START (poll {POLL}s, no orders) wallet={W[:10]}..")
    seen=set()
    try:
        for r in activity(200):
            if r.get("type")=="TRADE": seen.add(key(r))
        log(f"seeded {len(seen)} existing trades (only NEW ones will be measured)")
    except Exception as e:
        log(f"seed err {e}")
    while True:
        time.sleep(POLL)
        try: rows=activity(60)
        except Exception as e:
            log(f"poll err {str(e)[:60]}"); continue
        now=time.time()
        for r in rows:
            if r.get("type")!="TRADE": continue
            k=key(r)
            if k in seen: continue
            seen.add(k)
            side=str(r.get("side","")).upper(); px=float(r.get("price",0) or 0)
            tok=str(r.get("asset","")); ts=int(r.get("timestamp",0) or 0)
            slug=str(r.get("slug") or r.get("eventSlug") or "?")
            sz=float(r.get("size",0) or 0); usd=float(r.get("usdcSize",0) or 0)
            lat=round(now-ts,1) if ts else None
            bb,bbsz,ba,basz=book(tok)
            if side=="BUY":
                gap=round(ba-px,4) if ba is not None else None      # what WE pay above his fill
                avail=basz
            else:
                gap=round(px-bb,4) if bb is not None else None      # what WE lose selling below his fill
                avail=bbsz
            row={"ts":ts,"det_lat_s":lat,"side":side,"price":px,"size":sz,"usd":usd,"slug":slug,"token":tok,
                 "bid":bb,"bid_sz":bbsz,"ask":ba,"ask_sz":basz,"copy_gap":gap,"avail_sz":avail}
            open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")
            log(f"{side} {px:.3f} ${usd:.0f} {slug[:45]} | lat={lat}s gap={gap} avail={avail:.0f}sh (bid {bb}/ask {ba})")
        if len(seen)>5000: seen=set(list(seen)[-3000:])

if __name__=="__main__":
    main()
