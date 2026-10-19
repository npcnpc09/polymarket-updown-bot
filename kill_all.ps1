Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match "ws_paper_executor|ws_arb_observer|arb_scanner_observe|v8_mirror_sim"
} | Stop-Process -Force
Write-Output "all sims stopped"
