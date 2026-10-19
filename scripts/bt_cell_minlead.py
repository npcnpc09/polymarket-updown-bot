"""bt_cell_minlead.py — does a MIN |lead| gate on the cell exclude the low-vol/small-lead/chop air-pockets?
(A) REAL z-maker cell fills (0.90-0.95) split by |lead| at entry (in-sample, what motivated it).
(B) INDEPENDENT binance reconstruction: late (~165s) z>=2.5 & |lead|>=8 entries, settle win% by |lead| bucket
    and by the low-vol x small-lead combo. Win% is real-settle, fill/price-independent = the trustworthy read.
The air-pockets had |lead| 6.4-6.8 (below 8!) yet z 2.86-3.03 (inflated by vol~2.2). Gate candidate: cell
requires |lead|>=L (not just z>=2.5)."""
import json, math, time, httpx, statistics as st
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
# ---------- (A) real cell fills ----------
cell=[]
for o in (json.loads(l) for l in open(ROOT+"/data/multi_window_engine_live.jsonl",encoding="utf-8") if l.strip()):
    if o.get("filled") is True and o.get("won") is not None and o.get("B") and 0.90<=o["B"]<0.96 and o.get("lead") is not None:
        cell.append({"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),"lead":abs(o["lead"]),"vol":o.get("vol30"),"sh":o.get("sh")})
def repA(s,lab):
    if not s: print(f"  {lab:20s} n=0"); return
    w=sum(1 for r in s if r["won"]); p=sum(r["pnl"] for r in s)
    print(f"  {lab:20s} n={len(s):3d} win%={w/len(s)*100:5.1f} PnL=${p:+7.2f}")
print(f"=== (A) REAL z-maker CELL fills by |lead| (in-sample, n={len(cell)}) ===")
repA([r for r in cell if r["lead"]<10],"|lead|<10")
repA([r for r in cell if 10<=r["lead"]<14],"|lead| 10-14")
repA([r for r in cell if r["lead"]>=14],"|lead|>=14")
print("  -- the low-vol x small-lead danger cell --")
repA([r for r in cell if r["lead"]<12 and r["vol"] is not None and r["vol"]<5],"|lead|<12 & vol<5")
repA([r for r in cell if not(r["lead"]<12 and (r["vol"] or 9)<5)],"  (the rest)")

# ---------- (B) independent reconstruction ----------
COINS={"btc":"BTCUSDT","eth":"ETHUSDT"}; HOURS=72; ENTRY_OFF=165
now=int(time.time()); start=now-HOURS*3600
def fetch_1s(sym,t0,t1):
    out=[]; t=t0
    with httpx.Client(timeout=25) as c:
        while t<t1:
            k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1s","startTime":t*1000,"limit":1000}).json()
            if not isinstance(k,list) or not k: break
            for r in k: out.append((r[0]//1000,float(r[4])))
            t=k[-1][0]//1000+1
            if len(k)<1000: break
    return out
def vol30_at(c1m, ws):
    cl=[c1m.get(ws-60*i) for i in range(31)]; cl=[x for x in cl if x]
    if len(cl)<20: return None
    return st.pstdev([math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))])
recs=[]
for coin,sym in COINS.items():
    bars=fetch_1s(sym,start,now); P={t:px for t,px in bars}
    c1m={t:px for t,px in bars if t%60==0}
    W={}
    for t,px in bars:
        W.setdefault((t//300)*300,{})[t-(t//300)*300]=px
    for ws,pts in W.items():
        if 0 not in pts: continue
        opn=pts[0]; entry=None
        for d in range(ENTRY_OFF,ENTRY_OFF+4):
            if d in pts: entry=pts[d]; break
        settle=W.get(ws+300,{}).get(0) or pts.get(299)
        if entry is None or settle is None: continue
        vol=vol30_at(c1m,ws)
        if not vol or vol<=0: continue
        lead=math.log(entry/opn)*1e4
        if abs(lead)<8: continue
        z=abs(lead)/vol
        if z<2.5: continue
        recs.append({"won":((lead>=0)==(settle>=opn)),"lead":abs(lead),"vol":vol,"z":z})
def repB(s,lab):
    if not s: print(f"  {lab:24s} n=0"); return
    w=sum(1 for r in s if r["won"])
    print(f"  {lab:24s} n={len(s):4d} win%={w/len(s)*100:5.1f}")
print(f"\n=== (B) INDEPENDENT reconstruction: late z>=2.5 & |lead|>=8, {len(recs)} entries ({HOURS}h btc+eth) ===")
print(f"  base win% {sum(1 for r in recs if r['won'])/len(recs)*100:.1f}")
print("  by |lead|:")
repB([r for r in recs if r["lead"]<10],"|lead| 8-10")
repB([r for r in recs if 10<=r["lead"]<14],"|lead| 10-14")
repB([r for r in recs if 14<=r["lead"]<20],"|lead| 14-20")
repB([r for r in recs if r["lead"]>=20],"|lead|>=20")
print("  low-vol x small-lead danger combo:")
repB([r for r in recs if r["lead"]<12 and r["vol"]<5],"|lead|<12 & vol<5")
repB([r for r in recs if r["lead"]<12 and r["vol"]>=5],"|lead|<12 & vol>=5")
repB([r for r in recs if r["lead"]>=12],"|lead|>=12 (any vol)")
print("  candidate gates (KEEP set win% vs base):")
repB(recs,"ALL (no gate)")
repB([r for r in recs if r["lead"]>=10],"GATE |lead|>=10")
repB([r for r in recs if r["lead"]>=12],"GATE |lead|>=12")
print("\nREAD: gate helps if low-|lead| (esp. x low-vol) wins clearly LESS and dropping it lifts win%. If win%")
print("is flat across |lead| buckets -> the air-pockets' small lead was coincidence, gate would just cut volume.")
