"""Detached watcher: wait until 16:05 UTC, then run the paper-PnL resolver every
15 min until ~17:45 UTC, appending timestamped output to data/paper_pnl_settled.txt.
Captures the settlement curve robustly regardless of the interactive session."""
import time, subprocess, sys, os
from datetime import datetime, timezone, timedelta

OUT="data/paper_pnl_settled.txt"
RESOLVER="scripts/resolve_paper_pnl_6e1d.py"
PY=sys.executable

now=datetime.now(timezone.utc)
target=now.replace(hour=16,minute=5,second=0,microsecond=0)
if target<now: target=target+timedelta(days=1)  # safety, shouldn't trigger today

def log(msg):
    with open(OUT,"a",encoding="utf-8") as f: f.write(msg+"\n")

log(f"\n===== auto_resolve started {now.isoformat()} ; first run at {target.isoformat()} =====")
while datetime.now(timezone.utc) < target:
    time.sleep(60)

for i in range(8):   # ~16:05 .. 17:50, every 15 min
    ts=datetime.now(timezone.utc).isoformat()
    try:
        r=subprocess.run([PY,RESOLVER],capture_output=True,text=True,timeout=300)
        log(f"\n----- resolver run @ {ts} -----")
        log(r.stdout)
        if r.stderr.strip(): log("[stderr] "+r.stderr[-500:])
    except Exception as e:
        log(f"\n----- resolver run @ {ts} ERROR {e} -----")
    time.sleep(900)
log(f"\n===== auto_resolve done {datetime.now(timezone.utc).isoformat()} =====")
