"""Suitability check for restarting the maker. NEW logic (2026-06-07): gate on REGIME + LOSS STREAK,
NOT volatility. Reason: vol predicts win RATE (priced-in) not EV, and our biggest profit run ($59->$113)
was HIGH-vol -> vol<5 would have blocked it. The robust signal is that outcomes are STREAKY (loss->more
loss, win->more win; after 3+ DRY losses EV-1.31, after wins +0.19). So:
  SUITABLE (exit 0) iff regime_state != COLD  AND  win_streak >= 2  (2 consecutive DRY wins = warming,
  next-window EV +0.15 vs +0.13/breakeven after 1 win and -0.45 after a loss). else WAIT (exit 1).
  BTC vol still printed for info, not gating."""
import json,sys,os,math,statistics
WIN_WARM=2
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
state="UNKNOWN"; streak=99; wstreak=0; winslow=None
try:
    rs=json.load(open(os.path.join(ROOT,"data","regime_state.json")))
    state=rs.get("state","UNKNOWN"); streak=rs.get("loss_streak",99); wstreak=rs.get("win_streak",0); winslow=rs.get("win_slow")
except: pass
# vol for info only
vol=None
try:
    import httpx
    c=httpx.Client(timeout=12,headers={"User-Agent":"Mozilla/5.0"})
    k=c.get("https://api.binance.com/api/v3/klines",params={"symbol":"BTCUSDT","interval":"1m","limit":31}).json()
    cl=[float(x[4]) for x in k]
    vol=round(statistics.pstdev([math.log(cl[i]/cl[i-1])*1e4 for i in range(1,len(cl))]),2)
except: pass
suitable=(wstreak>=WIN_WARM)            # win_streak>=2 alone (regime-independent, per user 2026-06-07)
print("%s win_streak=%s regime=%s loss_streak=%s win24=%s vol=%s (need win_streak>=%d, regime-independent)"%(
    "SUITABLE" if suitable else "WAIT",wstreak,state,streak,("%.0f%%"%(winslow*100)) if winslow is not None else "?",vol,WIN_WARM))
sys.exit(0 if suitable else 1)
