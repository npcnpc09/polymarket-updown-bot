"""bt_resume_modes.py — backtest the three RESUME-TRIGGER modes as regime gates, held-out split.
A resume gate decides WHEN the engines are ON. Good gate = keeps most profit while cutting the bleed.
So we report, per mode: kept n / %kept / net-KEPT / net-FORGONE (skipped), on FULL / TRAIN(60%) / HELDOUT(40%).
Vol is logged on every fill (coin_vol30/vol30 -> 'vol'; btc_vol taker-only). ER/trend is NOT logged per fill,
so the pure trend mode can't be simulated here — noted in output (and ER forward-FAILED per memory).
Modes:
  A vol-based     : ON when vol < thr        (the OOS-validated axis)
  B trend-based   : ER gate — NOT BACKTESTABLE from fills (ER not logged); reported as such
  C hybrid        : ON when vol < thr AND flip60 < chopcap (taker subset, flip logged)
Sort by window-start for a clean time split."""
import json, statistics as st
ROOT="C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
rows=[]
for l in open(ROOT+"/data/early_taker_probe.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    try:o=json.loads(l)
    except:continue
    if o.get("kind")=="entry" and o.get("won") is not None:
        ws=ws_of(o.get("slug",""))
        if ws is None: continue
        rows.append({"ws":ws,"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),
                     "vol":o.get("coin_vol30"),"bvol":o.get("btc_vol"),"flip":o.get("flip60"),"eng":"taker"})
for l in open(ROOT+"/data/multi_window_engine_live.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    try:o=json.loads(l)
    except:continue
    if o.get("filled") and o.get("won") is not None and o.get("pnl") is not None:
        ws=ws_of(o.get("slug",""))
        if ws is None: continue
        rows.append({"ws":ws,"won":bool(o["won"]),"pnl":float(o.get("pnl",0) or 0),
                     "vol":o.get("vol30"),"bvol":None,"flip":None,"eng":"cell"})
rows.sort(key=lambda x:x["ws"])
n=len(rows); cut=int(n*0.6); train=rows[:cut]; held=rows[cut:]
base_f=sum(r["pnl"] for r in rows); base_tr=sum(r["pnl"] for r in train); base_hd=sum(r["pnl"] for r in held)
print(f"=== {n} fills | baseline net  FULL ${base_f:+.2f}  TRAIN ${base_tr:+.2f}  HELDOUT ${base_hd:+.2f} ===")
def seg(data, on):
    kept=[r for r in data if on(r)]; skip=[r for r in data if not on(r)]
    return len(kept), (len(kept)/len(data)*100 if data else 0), sum(r["pnl"] for r in kept), sum(r["pnl"] for r in skip)
def line(lab,on):
    kf,pf,nf,sf=seg(rows,on); kt,pt,nt,stt=seg(train,on); kh,ph,nh,sh=seg(held,on)
    print(f"  {lab:26s} FULL keep {pf:4.0f}% net${nf:+8.2f}(forgo${sf:+7.2f}) | TRAIN${nt:+8.2f} | HELDOUT keep{ph:4.0f}% net${nh:+8.2f}(forgo${sh:+7.2f})")
print("\n--- MODE A: vol-based (ON when coin/vol30 < thr) — all fills ---")
for thr in (4,5,6,6.5,7,8):
    line(f"vol < {thr}", lambda r,t=thr: r["vol"] is not None and r["vol"]<t)
print("    (vol is None on some -> treated as ON only if known<thr; None excluded from 'kept')")
print("\n--- MODE A2: btc_vol gate (taker subset only, memory VOL_CAP~6.5) ---")
tk=[r for r in rows if r["eng"]=="taker" and r["bvol"] is not None]
tkn=len(tk); tcut=int(tkn*0.6); ttr=tk[:tcut]; thd=tk[tcut:]
btr=sum(r["pnl"] for r in tk); btr_tr=sum(r["pnl"] for r in ttr); btr_hd=sum(r["pnl"] for r in thd)
print(f"   taker w/ btc_vol: {tkn} fills, baseline FULL ${btr:+.2f} TRAIN ${btr_tr:+.2f} HELDOUT ${btr_hd:+.2f}")
def linesub(lab,data,tr,hd,on):
    kf,pf,nf,sf=seg(data,on); kt,_,nt,_=seg(tr,on); kh,ph,nh,sh=seg(hd,on)
    print(f"  {lab:26s} FULL keep{pf:4.0f}% net${nf:+8.2f}(forgo${sf:+7.2f}) | TRAIN${nt:+8.2f} | HELDOUT keep{ph:4.0f}% net${nh:+8.2f}(forgo${sh:+7.2f})")
for thr in (5,6,6.5,7):
    linesub(f"btc_vol < {thr}",tk,ttr,thd, lambda r,t=thr: r["bvol"]<t)
print("\n--- MODE C: hybrid vol<thr AND flip60<chopcap (taker subset, flip logged) ---")
tf=[r for r in rows if r["eng"]=="taker" and r["vol"] is not None and r["flip"] is not None]
tfn=len(tf); fcut=int(tfn*0.6); ftr=tf[:fcut]; fhd=tf[fcut:]
fbf=sum(r["pnl"] for r in tf); fbtr=sum(r["pnl"] for r in ftr); fbhd=sum(r["pnl"] for r in fhd)
print(f"   taker w/ vol+flip: {tfn} fills, baseline FULL ${fbf:+.2f} TRAIN ${fbtr:+.2f} HELDOUT ${fbhd:+.2f}")
for vthr,fcap in [(6,0.55),(6.5,0.55),(6,0.50),(7,0.55)]:
    linesub(f"vol<{vthr} & flip<{fcap}",tf,ftr,fhd, lambda r,v=vthr,f=fcap: r["vol"]<v and r["flip"]<f)
print("\n--- MODE B: trend/ER gate — NOT BACKTESTABLE (ER not logged per fill); ER forward-FAILED per memory ---")
print("\nREAD: a resume gate is worth switching to ONLY if it keeps most profit (low forgo) AND improves/holds HELDOUT net.")
print("If a vol gate cuts the high-vol bleed on HELDOUT while forgoing little profit -> validated switch. Else keep as-is.")
