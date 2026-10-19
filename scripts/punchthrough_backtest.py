"""User's idea: identify the REVERSALS WITH ENOUGH MOMENTUM TO PUNCH THROUGH the 5m floor (window open
= settlement line), flipping us win->loss, vs harmless wobbles. For each live entry, reconstruct the
1-SECOND intra-window path (binance 1s klines) and measure:
  - punch_through: did price cross back through open against our side AND settle there (= the loss)
  - rev_vel: peak adverse velocity (bps/sec) of the move that broke through
  - early_adv: adverse move in the first 45s AFTER our entry (can we SEE the punch coming early?)
Compare winners vs losers: is the punch-through statistically separable / early-detectable?"""
import json,httpx,math,datetime
R=[]
for ln in open("data/multi_window_engine_live.jsonl",encoding="utf-8"):
    ln=ln.strip()
    if not ln: continue
    try: r=json.loads(ln)
    except: continue
    if "won" in r and "pnl" in r:
        try: r["_st"]=int(r["slug"].split("-")[-1])
        except: continue
        R.append(r)
SYM={"btc":"BTCUSDT","eth":"ETHUSDT"}
def kl1s(sym,t0,t1):
    out={}
    cur=t0
    while cur<t1:
        k=httpx.get("https://api.binance.com/api/v3/klines",params={"symbol":sym,"interval":"1s","startTime":cur*1000,"endTime":t1*1000,"limit":1000},timeout=20).json()
        if not isinstance(k,list) or not k: break
        for x in k: out[int(x[0]//1000)]=float(x[4])
        cur=int(k[-1][0]//1000)+1
        if len(k)<1000: break
    return out
rows=[]
for r in R:
    c=r["coin"]; st=r["_st"]; sym=SYM[c]
    d=kl1s(sym,st-2,st+302)
    if not d: continue
    ts=sorted(d);
    if len(ts)<60: continue
    op=d[ts[0]]; side=r["side"]; sgn=1 if side=="Up" else -1
    ent=st+180
    # path in bps from open, signed so + = in our favor
    def fav(t):
        p=None
        for dd in range(3):
            if t+dd in d: p=d[t+dd]; break
        if p is None: return None
        return sgn*math.log(p/op)*1e4
    # punch-through: min favorable value over the window (how far underwater it went through the floor)
    vals=[(t,sgn*math.log(d[t]/op)*1e4) for t in ts]
    minfav=min(v for _,v in vals)
    # peak adverse velocity over any 5s window (bps/sec) AFTER entry
    post=[(t,v) for t,v in vals if t>=ent]
    vel=0
    for i in range(len(post)):
        for j in range(i+1,len(post)):
            if post[j][0]-post[i][0]>5: break
            dv=post[i][1]-post[j][1]  # drop in favor = adverse
            dt=post[j][0]-post[i][0]
            if dt>0: vel=max(vel,dv/dt)
    # early adverse: favorable change in first 45s after entry (negative = moving against us early)
    e0=fav(ent); e45=fav(ent+45)
    early=(e45-e0) if (e0 is not None and e45 is not None) else None
    rows.append({"won":r["won"],"side":side,"B":r["B"],"entry_fav":round(e0,1) if e0 is not None else None,
                 "minfav":round(minfav,1),"rev_vel":round(vel,2),"early45":round(early,1) if early is not None else None})
W=[x for x in rows if x["won"]]; L=[x for x in rows if not x["won"]]
def avg(rs,k):
    v=[x[k] for x in rs if x[k] is not None]; return sum(v)/len(v) if v else 0
print("reconstructed %d windows (1s): %d win, %d loss\n"%(len(rows),len(W),len(L)))
print("%-6s %8s %10s %10s %10s"%("","entry_fav","min_fav","rev_vel","early45"))
print("%-6s %8.1f %10.1f %10.2f %10.1f"%("WIN",avg(W,"entry_fav"),avg(W,"minfav"),avg(W,"rev_vel"),avg(W,"early45")))
print("%-6s %8.1f %10.1f %10.2f %10.1f"%("LOSS",avg(L,"entry_fav"),avg(L,"minfav"),avg(L,"rev_vel"),avg(L,"early45")))
# does early45 (early adverse momentum) predict the loss?
print("\n--- can we SEE the punch coming in first 45s after entry? ---")
for lab,cond in (("early45 < -8 (sharp adverse early)",lambda x:x["early45"] is not None and x["early45"]<-8),
                 ("early45 -8..0 (mild adverse)",lambda x:x["early45"] is not None and -8<=x["early45"]<0),
                 ("early45 >= 0 (still in favor)",lambda x:x["early45"] is not None and x["early45"]>=0)):
    s=[x for x in rows if cond(x)]
    if s: print("  %-34s n=%-3d win=%2.0f%%"%(lab,len(s),sum(1 for x in s if x["won"])/len(s)*100))
print("\n--- peak reversal velocity vs outcome ---")
for lo,hi in ((0,1),(1,2),(2,4),(4,99)):
    s=[x for x in rows if lo<=x["rev_vel"]<hi]
    if s: print("  rev_vel %g-%g bps/s: n=%-3d win=%2.0f%%"%(lo,hi,len(s),sum(1 for x in s if x["won"])/len(s)*100))
