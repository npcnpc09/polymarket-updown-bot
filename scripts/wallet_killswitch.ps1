# wallet_killswitch.ps1 — WALLET-LEVEL MASTER KILL SWITCH (added 2026-06-30, user-approved)
# Watches the REAL shared wallet (data/wallet_log.jsonl total), independent of the engines'
# per-engine optimistic 'realized' tallies. Trips when drawdown from the all-time peak exceeds
# DD_LIMIT, confirmed over CONFIRM distinct wallet readings (~5 min apart). On trip: hard-kills
# every python process whose command line contains '--place' (the 3 live engines), leaving
# wallet_logger + DRY engines alive. Open positions are hold-to-settle so they redeem on-chain
# regardless. Does NOT restart anything. Writes HALTED.marker.
#
# WHY: per-engine STOP_LOSS (-30 / -15) checks each engine's OWN computed PnL, which is split
# across 3 engines sharing one wallet AND under-records losses (jsonl logging gap). No single
# engine number reaches its stop while the real wallet bleeds. This reads the true wallet.

$ErrorActionPreference = "Continue"
$Root      = Split-Path -Parent $PSScriptRoot
$WalletLog = Join-Path $Root "data\wallet_log.jsonl"
$KillLog   = Join-Path $Root "data\killswitch.log"
$Marker    = Join-Path $Root "data\HALTED.marker"

$DD_LIMIT  = 55.0    # trip if (smoothed peak - smoothed current) exceeds this. Raised 35->55 after a
                     # 2ND false trip 07-08 14:33: redemption-relayer lag (04:00-17:00) made open_val
                     # chronically UNDERCOUNT won-but-unredeemed positions -> total read ~$38 low for ~1h
                     # (median smoothing can't filter a sustained undercount) while cell settled +$5.35.
                     # We HOLD-TO-SETTLE (never sell) -> mark-to-market/valuation-lag drawdown is NOT
                     # actionable; only a sustained REAL settled bleed should trip. $55 + long confirm.
$POLL_SEC  = 60      # poll interval
$CONFIRM   = 25      # readings below trip line before killing (~25 min). Real bleed is slow & persists;
                     # mark-to-market + redemption-lag undercounts self-heal within a settle/redeem cycle.

# 2026-07-08 FIX (false trip): wallet_log 'total' includes mark-to-market of OPEN positions, which
# spikes transiently (one 20sh cell position swung $366<->$396 intra-window). The OLD code set peak =
# raw max, so a single transient HIGH mark ($396.35) inflated the trip-line and a transient LOW mark
# ($366.04, stuck 40min) breached it while the engines were WINNING. Fix: smooth with a rolling
# median so single-point transient spikes set neither peak nor breach.
function Median($arr) {
  if ($arr.Count -eq 0) { return $null }
  $s = $arr | Sort-Object; $n = $s.Count
  if ($n % 2 -eq 1) { return [double]$s[[int](($n-1)/2)] }
  return ([double]$s[$n/2-1] + [double]$s[$n/2]) / 2.0
}

function Log($m) {
  Add-Content -Path $KillLog -Value ("[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "] " + $m) -Encoding utf8
}

# RESUME baseline: only measure drawdown from NOW onward (peak = max total since this start), so the old
# all-time peak ($443) doesn't instant-trip. Seeded at launch; peak rises if the wallet makes new highs after resume.
$BaselineTs = [int][double]::Parse((Get-Date -UFormat %s))
Log ("killswitch START: DD_LIMIT=" + $DD_LIMIT + " poll=" + $POLL_SEC + "s confirm=" + $CONFIRM + " baseline_ts=" + $BaselineTs + " (drawdown measured from resume, not all-time peak)")
$lastTs   = 0
$breaches = 0

while ($true) {
  try {
    $rows = Get-Content $WalletLog -ErrorAction Stop | ForEach-Object { try { $_ | ConvertFrom-Json } catch {} } | Where-Object { $_.total -ne $null -and $_.ts -ne $null }
    if ($rows) {
      $last = $rows | Select-Object -Last 1
      if ($last.ts -ne $lastTs) {
        $lastTs = $last.ts
        $sinceResume = @($rows | Where-Object { [int]$_.ts -ge $BaselineTs })
        # rolling 3-point median series: filters single-point transient marks on BOTH ends
        $totals = @($sinceResume | ForEach-Object { [double]$_.total })
        $smooth = @()
        for ($i = 0; $i -lt $totals.Count; $i++) {
          $lo = [math]::Max(0, $i - 2)
          $smooth += (Median $totals[$lo..$i])
        }
        if ($smooth.Count -eq 0) { $smooth = @([double]$last.total) }
        $cur  = [math]::Round($smooth[-1], 2)                                   # smoothed current
        $peak = [math]::Round(($smooth | Measure-Object -Maximum).Maximum, 2)   # peak of SMOOTHED series
        $dd   = [math]::Round($peak - $cur, 2)
        $trip = [math]::Round($peak - $DD_LIMIT, 2)
        if (($peak - $cur) -gt $DD_LIMIT) {
          $breaches++
          Log ("BREACH " + $breaches + "/" + $CONFIRM + ": total=" + $cur + " peak=" + $peak + " dd=" + $dd + " over limit " + $DD_LIMIT + " (trip-line " + $trip + ")")
          if ($breaches -ge $CONFIRM) {
            Log "=== TRIPPED - killing all --place engines ==="
            $procs = @(Get-WmiObject Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*--place*" })
            foreach ($p in $procs) {
              Log ("KILL pid=" + $p.ProcessId + " :: " + ($p.CommandLine -replace '\s+',' ').Trim())
              Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
            }
            Start-Sleep 2
            $left = @(Get-WmiObject Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*--place*" })
            Log ("post-kill: " + $left.Count + " --place engines remaining")
            Set-Content -Path $Marker -Value ("HALTED " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + " total=" + $cur + " peak=" + $peak + " dd=" + $dd + " by wallet_killswitch") -Encoding utf8
            Log "=== HALT complete. Engines down (no auto-restart). killswitch exiting. ==="
            break
          }
        } else {
          if ($breaches -gt 0) { Log ("recovered: total=" + $cur + " dd=" + $dd + " within limit -> reset breaches") }
          $breaches = 0
          Log ("ok: total=" + $cur + " peak=" + $peak + " dd=" + $dd + " trip-line " + $trip + " buffer " + [math]::Round($cur - $trip, 2))
        }
      }
    }
  } catch {
    Log ("ERROR: " + $_.Exception.Message)
  }
  Start-Sleep $POLL_SEC
}
