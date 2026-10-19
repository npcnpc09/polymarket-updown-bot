# Adds the maker_live_test --place allow rule to the user's Claude settings.
# Run by the USER (their hand grants the permission). Idempotent; prints confirmation.
$ErrorActionPreference = "Stop"
$p = Join-Path $HOME ".claude\settings.json"
$rule = "Bash(python scripts/maker_live_test.py --place:*)"
if (Test-Path $p) {
    $j = Get-Content $p -Raw | ConvertFrom-Json
} else {
    $j = [pscustomobject]@{}
}
# rebuild a clean permissions block with exactly the one rule
$j | Add-Member -NotePropertyName permissions -NotePropertyValue ([pscustomobject]@{ allow = @($rule) }) -Force
$j | ConvertTo-Json -Depth 6 | Set-Content $p -Encoding utf8
# verify
$check = (Get-Content $p -Raw | ConvertFrom-Json).permissions.allow -contains $rule
Write-Output "settings written to: $p"
Write-Output "rule present (clean): $check"
Get-Content $p -Raw
