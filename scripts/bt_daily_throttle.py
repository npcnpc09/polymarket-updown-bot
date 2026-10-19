"""bt_daily_throttle.py — would a DAY-LEVEL adaptive throttle (reduce size after down days, restore after
up days) beat always-full-size? Tests on REAL combined daily PnL. Key risk: if down days are followed by
VIOLENT up recoveries (mean-reverting daily PnL), throttling de-risks INTO the recovery = hurts.
(1) day-level PnL autocorrelation. (2) throttle sim: after a down day, next day at HALF size."""
import json, re, statistics as st
from datetime import datetime, timezone
ROOT = "C:/Users/Administrator/Desktop/polymarket_arb_deploy_full"
def daypnl(f, kind):
    out = {}
    for o in (json.loads(l) for l in open(ROOT+"/"+f, encoding="utf-8") if l.strip()):
        ok = (o.get("kind") == "entry") if kind == "taker" else (o.get("filled") is True)
        if ok and o.get("won") is not None and o.get("pnl") is not None:
            m = re.search(r"-5m-(\d+)", o.get("slug", ""))
            if not m: continue
            d = datetime.fromtimestamp(int(m.group(1)), timezone.utc).strftime("%m-%d")
            out[d] = out.get(d, 0.0)+float(o["pnl"])
    return out
zm = daypnl("data/multi_window_engine_live.jsonl", "maker"); tk = daypnl("data/early_taker_probe.jsonl", "taker")
days = sorted(set(zm) | set(tk))
comb = [(d, zm.get(d, 0)+tk.get(d, 0)) for d in days]
print("=== combined daily PnL ===")
for d, p in comb: print(f"  {d}: {p:+.2f}")
seq = [p for d, p in comb]
# (1) day-level autocorrelation: after a DOWN day, what's the next day?
print("\n=== (1) after a DOWN day, next-day PnL (clustering vs mean-reversion?) ===")
after_down = [seq[i+1] for i in range(len(seq)-1) if seq[i] < 0]
after_up = [seq[i+1] for i in range(len(seq)-1) if seq[i] >= 0]
if after_down: print(f"  next-day after DOWN day: avg={st.mean(after_down):+.2f} (n={len(after_down)}) -> {'UP=mean-reverting' if st.mean(after_down)>0 else 'DOWN=clustering'}")
if after_up: print(f"  next-day after UP day:   avg={st.mean(after_up):+.2f} (n={len(after_up)})")
# lag-1 autocorrelation
m = st.mean(seq); num = sum((seq[i]-m)*(seq[i-1]-m) for i in range(1, len(seq))); den = sum((x-m)**2 for x in seq)
print(f"  lag-1 autocorr of daily PnL = {num/den if den else 0:+.2f}  (negative = mean-reverting = throttle HURTS)")
# (2) throttle sim: after a down day, next day at HALF size; restore after an up day
print("\n=== (2) throttle sim: after a down day -> next day HALF size ===")
base = sum(seq); thr = 0.0; size = 1.0
for i in range(len(seq)):
    thr += seq[i]*size
    size = 0.5 if seq[i] < 0 else 1.0
print(f"  always-full: ${base:+.2f}  |  throttle(half-after-down): ${thr:+.2f}  |  delta: ${thr-base:+.2f}")
# also a 'reduce after combined drawdown' variant (trailing 3-day)
print("\n=== (3) throttle on trailing-2day drawdown -> half size ===")
thr2 = 0.0;
for i in range(len(seq)):
    dd = sum(seq[max(0, i-2):i])  # prior 2 days
    size = 0.5 if (i >= 2 and dd < 0) else 1.0
    thr2 += seq[i]*size
print(f"  throttle(half-after-2day-drawdown): ${thr2:+.2f}  |  delta vs full: ${thr2-base:+.2f}")
print("\nREAD: if deltas are NEGATIVE, day-level throttling HURTS (it de-risks into the violent recoveries).")
print("Then the right adaptivity is FAST (trade-level breaker), not slow (day-level). n=13 days = illustrative.")
