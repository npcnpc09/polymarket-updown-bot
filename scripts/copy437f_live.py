"""COPY-TRADE executor for 0x437f (Shanghai weather trader). Built 2026-07-02; small-size validation.
DRY by default; --place = real money. Mirrors his BUYs (with a copy-tax gate) and exits when he SELLs,
using sell_with_escalation (chase bid, floor, hold-to-settle fallback).

Risk caps (validation size): ORDER_USD~$5/trade, MAX_EXPOSURE $30, DAILY_STOP -$10.
Entry gate: only take the ask if ask <= his_fill + MAX_TAX (default 0.03). Backtest: +10.6% ROI at 3c/leg.
-> data/copy437f_live.jsonl / .log"""
import json, time, os, sys, urllib.request, datetime, collections

W="0x437f1c745a4abd87d5a9a2c61294139d86005b95"
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,os.path.join(ROOT,"scripts"))
PLACE=("--place" in sys.argv)
def _argval(k,d):
    return sys.argv[sys.argv.index(k)+1] if k in sys.argv and sys.argv.index(k)+1<len(sys.argv) else d
ORDER_USD=float(_argval("--orderusd","5"))
MAX_TAX=float(_argval("--maxtax","0.03"))
MAX_EXPOSURE=float(_argval("--maxexpo","30"))
DAILY_STOP=float(_argval("--dailystop","-10"))
POLL=12
_sfx="" if PLACE else "_dry2"
OUTF=os.path.join(ROOT,"data",f"copy437f_live{_sfx}.jsonl"); LOGF=os.path.join(ROOT,"data",f"copy437f_live{_sfx}.log")

def log(m):
    line=f"[{datetime.datetime.utcnow().strftime('%m-%d %H:%M:%S')}] {m}"
    print(line,flush=True)
    try: open(LOGF,"a",encoding="utf-8").write(line+"\n")
    except: pass
def rec(row):
    row["ts_rec"]=int(time.time()); row["live"]=PLACE
    open(OUTF,"a",encoding="utf-8").write(json.dumps(row)+"\n")

def get(url,timeout=15):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req,timeout=timeout).read())
def activity(limit=60):
    return get(f"https://data-api.polymarket.com/activity?user={W}&limit={limit}")
def book_raw(token):
    try:
        b=get(f"https://clob.polymarket.com/book?token_id={token}",timeout=10)
        bids=sorted(((float(x["price"]),float(x["size"])) for x in b.get("bids",[]) if float(x["size"])>0),key=lambda z:z[0])
        asks=sorted(((float(x["price"]),float(x["size"])) for x in b.get("asks",[]) if float(x["size"])>0),key=lambda z:z[0])
        bb=bids[-1] if bids else (None,0.0); ba=asks[0] if asks else (None,0.0)
        return bb[0],bb[1],ba[0],ba[1]
    except Exception: return None,0.0,None,0.0
def key(r): return f"{r.get('transactionHash','')}_{r.get('asset','')}_{r.get('timestamp','')}_{r.get('side','')}"

def main():
    from sell_helper import client, sell_with_escalation
    cli=client() if PLACE else None
    log(f"copy437f {'LIVE (--place)' if PLACE else 'DRY'} START orderUSD={ORDER_USD} maxTax={MAX_TAX} maxExpo={MAX_EXPOSURE} dailyStop={DAILY_STOP}")
    seen=set(); inv={}   # token -> dict(sh, px, slug)
    day=datetime.datetime.utcnow().strftime("%m-%d"); day_pnl=0.0; halted=False
    try:
        for r in activity(200):
            if r.get("type")=="TRADE": seen.add(key(r))
        log(f"seeded {len(seen)} old trades")
    except Exception as e: log(f"seed err {e}")
    while True:
        time.sleep(POLL)
        d=datetime.datetime.utcnow().strftime("%m-%d")
        if d!=day: day=d; day_pnl=0.0; halted=False; log(f"new day, pnl reset")
        try: rows=activity(60)
        except Exception as e: log(f"poll err {str(e)[:60]}"); continue
        for r in rows:
            if r.get("type")!="TRADE": continue
            k=key(r)
            if k in seen: continue
            seen.add(k)
            side=str(r.get("side","")).upper(); hpx=float(r.get("price",0) or 0)
            tok=str(r.get("asset","")); slug=str(r.get("slug") or "?")
            husd=float(r.get("usdcSize",0) or 0)
            if side=="BUY":
                if halted: log(f"skip BUY (daily-stopped) {slug[:40]}"); continue
                expo=sum(v["sh"]*v["px"] for v in inv.values())
                if expo+ORDER_USD>MAX_EXPOSURE: log(f"skip BUY (exposure {expo:.0f}+{ORDER_USD}>{MAX_EXPOSURE}) {slug[:40]}"); continue
                bb,bbsz,ba,basz=book_raw(tok)
                if ba is None: rec({"act":"skip_buy","why":"no_ask","slug":slug,"his_px":hpx}); continue
                tax=round(ba-hpx,4)
                if tax>MAX_TAX:
                    log(f"skip BUY tax {tax:.3f}>{MAX_TAX} {slug[:40]} (his {hpx} ask {ba})")
                    rec({"act":"skip_buy","why":"tax","tax":tax,"slug":slug,"his_px":hpx,"ask":ba}); continue
                size=max(5,round(ORDER_USD/ba))
                if basz<size:
                    log(f"skip BUY depth {basz:.0f}<{size} {slug[:40]}")
                    rec({"act":"skip_buy","why":"depth","slug":slug,"ask_sz":basz}); continue
                if PLACE:
                    try:
                        resp=cli.place_limit_order(token_id=tok,price=ba,size=size,side="BUY",post_only=False)
                        oid=getattr(resp,"order_id",None) or getattr(resp,"id",None)
                        if not oid: log(f"BUY rejected {slug[:40]}: {getattr(resp,'error_msg',None)}"); continue
                    except Exception as e: log(f"BUY exc {str(e)[:80]}"); continue
                cur=inv.get(tok,{"sh":0.0,"px":0.0,"slug":slug})
                tot=cur["sh"]+size
                cur["px"]=(cur["sh"]*cur["px"]+size*ba)/tot; cur["sh"]=tot; cur["slug"]=slug
                inv[tok]=cur
                log(f"COPY BUY {size}sh @ {ba} (his {hpx}, tax {tax:.3f}) {slug[:45]}")
                rec({"act":"buy","sh":size,"px":ba,"his_px":hpx,"tax":tax,"slug":slug,"token":tok})
            elif side=="SELL" and tok in inv:
                pos=inv[tok]
                bb,bbsz,ba,basz=book_raw(tok)
                floor=max(0.01,hpx-0.03)
                if PLACE:
                    res=sell_with_escalation(cli,tok,pos["sh"],floor,log=log)
                    sold=res["sold"]; avg=res["avg_px"] or 0.0
                else:
                    sold=pos["sh"] if (bb is not None and bb>=floor) else 0.0; avg=bb or 0.0
                    res={"sold":sold,"remaining":pos["sh"]-sold,"avg_px":avg,"gave_up_reason":None if sold else "dry_bid<floor"}
                pnl=(sold*(avg-pos["px"])) if sold>0 else 0.0
                day_pnl+=pnl
                log(f"COPY SELL {sold}/{pos['sh']}sh @ {avg} (entry {pos['px']:.3f}, his {hpx}) pnl={pnl:+.2f} dayPnl={day_pnl:+.2f} {pos['slug'][:40]}")
                rec({"act":"sell","sold":sold,"remaining":res["remaining"],"avg_px":avg,"entry_px":pos["px"],"his_px":hpx,"pnl":round(pnl,2),"slug":pos["slug"],"token":tok,"gave_up":res["gave_up_reason"]})
                if res["remaining"]<=1e-6: inv.pop(tok,None)
                else: inv[tok]["sh"]=res["remaining"]   # unsold remainder -> hold to settle
                if day_pnl<=DAILY_STOP and not halted:
                    halted=True; log(f"=== DAILY STOP {day_pnl:+.2f} <= {DAILY_STOP} — no new buys today ===")
        if len(seen)>5000: seen=set(list(seen)[-3000:])

if __name__=="__main__":
    main()
