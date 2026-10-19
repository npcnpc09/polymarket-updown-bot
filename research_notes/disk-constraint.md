---
name: disk-constraint
description: "This server's C: drive is small (29.5GB) and runs near-full; watch space before heavy installs"
metadata: 
  node_type: memory
  type: project
  originSessionId: 0e469908-f25e-4a0e-a456-e7cca9d64a7e
---

The deploy server has a **29.5 GB C: drive** and only **3.83 GB RAM** — disk runs critically tight (was down to ~270 MB free on 2026-05-31). The Desktop project folder (`polymarket_arb_deploy_full`) alone is ~3.7 GB.

**Why:** Heavy installs (Playwright browsers, pip packages, Windows updates) can easily exhaust the drive.

**How to apply:** Before installing large deps, check free space (`(New-Object System.IO.DriveInfo('C')).AvailableFreeSpace`). Reclaim space via: DISM `/StartComponentCleanup /ResetBase`, clearing `%windir%\SoftwareDistribution\Download`, Edge update downloads, pip cache, and temp dirs. WinRE active copy lives on a separate recovery partition (partition3), so the C: `Recovery\WindowsRE` copy is an orphan that can be deleted. Pagefile is system-managed (~3.4 GB) — don't shrink given low RAM.
