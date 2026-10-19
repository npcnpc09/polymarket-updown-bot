"""fee_reconcile.py — are there fees on our 5m/15m updown trades? Our logged pnl assumes a winning share pays
exactly $1.00 (pnl = sh*(1-B) win / -sh*B loss). If Polymarket charges a fee, actual wallet change would be
LOWER than summed logged pnl. Reconcile: sum logged pnl across all engines over a window vs the wallet delta
over the same window (no injection in the window). A persistent shortfall beyond redemption-lag noise = fees."""
import json
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def ws_of(s):
    try: return int(s.rsplit("-",1)[1])
    except: return None
# wallet series
wl=[json.loads(l) for l in open(ROOT+"/data/wallet_log.jsonl",encoding="utf-8") if l.strip()]
wl.sort(key=lambda x:x["ts"])
# pick a window: last ~36h
t1=wl[-1]["ts"]; t0=t1-36*3600
w0=min(wl,key=lambda x:abs(x["ts"]-t0)); w1=wl[-1]
print(f"window: {w0['ts']} -> {w1['ts']}  ({(w1['ts']-w0['ts'])/3600:.1f}h)")
print(f"wallet total: ${w0['total']:.2f} -> ${w1['total']:.2f}  delta=${w1['total']-w0['total']:+.2f}")
# sum logged pnl across engines, by SETTLE time approx (ws+dur). Use ws in [t0,t1] as proxy.
srcs=[("data/multi_window_engine_live.jsonl",300,lambda o:o.get("filled") is True and o.get("won") is not None),
      ("data/multi_window_engine_15m_live.jsonl",900,lambda o:o.get("filled") is True and o.get("won") is not None),
      ("data/multi_window_engine_sol_live.jsonl",300,lambda o:o.get("filled") is True and o.get("won") is not None),
      ("data/early_taker_probe.jsonl",300,lambda o:o.get("kind")=="entry" and o.get("won") is not None)]
tot=0.0; nfill=0; byeng={}
for f,dur,keep in srcs:
    s=0.0; n=0
    try:
        for o in (json.loads(l) for l in open(ROOT+"/"+f,encoding="utf-8") if l.strip()):
            if keep(o):
                w=ws_of(o.get("slug",""))
                if w and t0<=w+dur<=t1:   # settled within window
                    s+=float(o.get("pnl",0) or 0); n+=1
    except FileNotFoundError: pass
    byeng[f.split("_")[-1].replace(".jsonl","").replace("live","").strip("_") or f]= (n,s)
    tot+=s; nfill+=n
for k,(n,s) in byeng.items(): print(f"  {k:18s} fills={n:3d} logged pnl=${s:+8.2f}")
print(f"\nsum LOGGED pnl (settled in window): ${tot:+.2f}  over {nfill} fills")
print(f"actual WALLET delta:               ${w1['total']-w0['total']:+.2f}")
gap=(w1['total']-w0['total'])-tot
print(f"GAP (wallet - logged):             ${gap:+.2f}")
print(f"\nREAD: gap ~0 (within redemption-lag/open-position noise) = NO material fee; winning shares pay ~$1.00.")
print("A large persistent NEGATIVE gap (wallet < logged) would indicate a fee/haircut on settlement.")
print(f"(note: open_val at window edges = ${w0.get('open_val',0):.2f} -> ${w1.get('open_val',0):.2f}; nonzero shifts the gap = timing, not fee.)")
