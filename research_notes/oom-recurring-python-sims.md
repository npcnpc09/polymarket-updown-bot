---
name: oom-recurring-python-sims
description: Recurring OOM cause — too many concurrent Python sims; recovery recipe when taskkill hangs
metadata: 
  node_type: memory
  type: project
  originSessionId: d74533f0-28b2-4d13-b9b2-49a037e00a62
---

The box runs out of RAM repeatedly because `run_all.ps1` starts **4 persistent Python sims at once** (ws_paper_executor, ws_arb_observer, arb_scanner_observe, v8_mirror_sim), and ad-hoc runs like the overnight `fill_rate_test` add more. 5+ resident Python interpreters on the 3.83 GB box ([[disk-constraint]]) tip it into pagefile thrash.

**Why:** each Python + websocket/data libs is ~100-400 MB; total exceeds physical RAM, so the kernel thrashes and even `tasklist`/`Get-Process`/`taskkill /IM` time out (they must walk the process table).

**How to apply:**
- Recovery when thrashing: `taskkill /F /PID <pid>` for a known PID (e.g. from a `.pid` file) often lands even if it reports a timeout — freeing one process makes the table walkable again. Then `Get-Process -Name python` + `$_.Kill()` clears the rest. `.NET GetProcessById($pid).Kill()` works where taskkill's RPC times out.
- Lightweight RAM check that survives thrash: `Get-Counter '\Memory\Available MBytes'` (full `Get-Process | Sort WorkingSet` / WMI hangs under pressure).
- Prevention: don't run all 4 sims + overnight tests at once. Run 1-2 concurrently; use `.\kill_all.ps1` before starting a new batch. Healthy idle = ~2.4 GB free.
