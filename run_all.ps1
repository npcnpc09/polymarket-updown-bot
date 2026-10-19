# Start all 4 sims in parallel. Windows PowerShell.
# Requires: $env:POLY_PK and $env:POLY_PROXY set, OR .env file in this directory.

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

# Load .env if exists
$envFile = Join-Path $ROOT ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^([A-Z_]+)=(.+)$") {
            Set-Item "env:$($Matches[1])" $Matches[2].Trim()
        }
    }
}

if (-not $env:POLY_PK -or -not $env:POLY_PROXY) {
    Write-Error "POLY_PK and POLY_PROXY env vars not set. Copy .env.example to .env or set in this shell."
    exit 1
}

$DATA = Join-Path $ROOT "data"
if (-not (Test-Path $DATA)) { New-Item -ItemType Directory $DATA | Out-Null }
Set-Location $DATA

Write-Output "=== Starting 4 sims ==="

Start-Process python -ArgumentList "$ROOT\scripts\ws_paper_executor.py" -RedirectStandardOutput "ws_paper_executor.log" -RedirectStandardError "ws_paper_executor.err" -NoNewWindow -PassThru | ForEach-Object { "  ws_paper_executor    PID $($_.Id)" }

Start-Process python -ArgumentList "$ROOT\scripts\ws_arb_observer.py" -RedirectStandardOutput "ws_observer.log" -RedirectStandardError "ws_observer.err" -NoNewWindow -PassThru | ForEach-Object { "  ws_arb_observer      PID $($_.Id)" }

Start-Process python -ArgumentList "$ROOT\scripts\arb_scanner_observe.py","--interval","8" -RedirectStandardOutput "arb_scanner.log" -RedirectStandardError "arb_scanner.err" -NoNewWindow -PassThru | ForEach-Object { "  arb_scanner_observe  PID $($_.Id)" }

Start-Process python -ArgumentList "$ROOT\scripts\v8_mirror_sim.py","--interval","10" -RedirectStandardOutput "v8_mirror.log" -RedirectStandardError "v8_mirror.err" -NoNewWindow -PassThru | ForEach-Object { "  v8_mirror_sim        PID $($_.Id)" }

Write-Output ""
Write-Output "Monitor:  Get-Content -Tail 20 -Wait data\ws_paper_executor.log"
Write-Output "Stop:     .\kill_all.ps1"
