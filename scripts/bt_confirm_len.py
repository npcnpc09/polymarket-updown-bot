"""bt_confirm_len.py — does a LONGER / sustained within-window confirm filter out the 'bought the early-pop
top then reversed' losers? Reconstruct 5m windows from binance 1s klines. For each window find the FIRST
|lead|>=8 cross (offset<=180s), then test confirm rules at +15/30/45/60s and a 'no-rollback' (lead didn't
fade) variant. Settle = close@300s vs open.

CAVEAT (read RELATIVE not absolute): binance reconstruction inflates win% & understates Chainlink-settle
reversals ([[backtests-untrustworthy-even-realistic-crossval]]). Valid use = compare confirm-15 vs longer on
the SAME data (does a longer confirm REMOVE losers?), NOT the absolute win%."""
import httpx, math, time, sys, statistics as st
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}
HOURS=float(sys.argv[1]) if len(sys.argv)>1 else 36.0
LEAD_TRIG=8.0; MAX_OFFSET=180
now=int(time.time()); start=now-int(HOURS*3600)
def fetch_1s(sym, t0, t1):
    out=[]; t=t0
    with httpx.Client(timeout=20) as c:
        while t<t1:
            k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1s","startTime":t*1000,"limit":1000}).json()
            if not isinstance(k,list) or not k: break
            for row in k: out.append((row[0]//1000, float(row[4])))  # (sec, close)
            t=k[-1][0]//1000 + 1
            if len(k)<1000: break
    return out
def windows(bars):
    W={}
    for sec,px in bars:
        ws=(sec//300)*300; W.setdefault(ws,{})[sec-ws]=px
    return W
def lead(px,opn): return math.log(px/opn)*1e4
RULES=["C15","C30","C45","C60","C15_norb","C30_norb","C45_norb","C60_norb","C30_rising"]
agg={r:{"n":0,"w":0} for r in RULES}
base={"n":0,"w":0}; filtered_by={r:{"drop_loss":0,"drop_win":0} for r in RULES}
nwin=0
for coin,sym in COINS.items():
    bars=fetch_1s(sym,start,now); W=windows(bars)
    for ws,pts in W.items():
        if 0 not in pts: continue
        # settle price = last second of window (~299), or next window's open if present
        settle_px = W.get(ws+300,{}).get(0) or pts.get(299) or pts.get(298) or pts.get(297)
        if settle_px is None: continue
        opn=pts[0]; pts[300]=settle_px; nwin+=1
        # first cross
        cross=None
        for off in range(1,MAX_OFFSET+1):
            if off in pts and abs(lead(pts[off],opn))>=LEAD_TRIG:
                cross={"off":off,"lead":lead(pts[off],opn),"side":(pts[off]>=opn)}; break
        if not cross: continue
        settle_up=(pts[300]>=opn)
        def leadat(o):
            for d in range(o,o+3):  # tolerate tiny gaps
                if d in pts: return lead(pts[d],opn)
            return None
        # baseline C15 = current rule
        l15=leadat(cross["off"]+15)
        c15_ok = l15 is not None and abs(l15)>=LEAD_TRIG and (l15>=0)==cross["side"]
        if c15_ok:
            base["n"]+=1; won=(cross["side"]==settle_up)
            if won: base["w"]+=1
        for r in RULES:
            sec=int(r[1:3].rstrip("_") if r[1:3].rstrip("_").isdigit() else r[1:3]) if False else int("".join(ch for ch in r if ch.isdigit()))
            l=leadat(cross["off"]+sec)
            ok = l is not None and abs(l)>=LEAD_TRIG and (l>=0)==cross["side"]
            if "norb" in r:  # no-rollback: lead at confirm >= lead at cross (magnitude held/grew)
                ok = ok and abs(l)>=abs(cross["lead"])
            if "rising" in r:  # strictly grew vs cross (sustained up-build)
                ok = ok and abs(l)>abs(cross["lead"])+0.5
            if ok:
                agg[r]["n"]+=1; won=(cross["side"]==settle_up)
                if won: agg[r]["w"]+=1
            # vs C15: did this rule DROP a C15 entry, and was it a loser?
            if c15_ok and not ok:
                won15=(cross["side"]==settle_up)
                if won15: filtered_by[r]["drop_win"]+=1
                else: filtered_by[r]["drop_loss"]+=1
print(f"windows reconstructed: {nwin} | confirm-cross+settle sample below")
print(f"\nCAVEAT: absolute win% INFLATED by reconstruction; read the DELTA (longer vs C15) and drop-loss/drop-win.\n")
print(f"{'rule':12s} {'n':>4s} {'win%':>6s} | dropped-from-C15: {'losers':>6s} {'winners':>7s}  (good filter = drops losers, keeps winners)")
b=base
print(f"{'C15(base)':12s} {b['n']:4d} {b['w']/b['n']*100 if b['n'] else 0:6.1f} |")
for r in RULES:
    a=agg[r]; wr=a["w"]/a["n"]*100 if a["n"] else 0
    f=filtered_by[r]; dl,dw=f["drop_loss"],f["drop_win"]
    rat=f"{dl}/{dl+dw} ({dl/(dl+dw)*100:.0f}% of drops were losers)" if (dl+dw)>0 else "—"
    print(f"{r:12s} {a['n']:4d} {wr:6.1f} | drops {dl:3d} losers, {dw:3d} winners   {rat}")
print("\nREAD: a longer/no-rollback confirm HELPS only if win% rises meaningfully AND the entries it drops")
print("from C15 are mostly LOSERS (high % losers in drops). If it drops winners too -> it's just cutting volume.")
