# demo_p5.ps1 — thin PowerShell wrapper over demo_p5.py (real UI/service path)
$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
if (-not $RepoRoot) { $RepoRoot = (Get-Location).Path }
Set-Location $RepoRoot
Write-Host "============================================"
Write-Host " P5 VISIBLE PRODUCT EXPERIENCE DEMO"
Write-Host "============================================"
Write-Host "Repo: $RepoRoot"
python demo_p5.py
if ($LASTEXITCODE -ne 0) { Write-Error "demo_p5.py failed with $LASTEXITCODE"; exit 1 }
Write-Host "demo_p5.ps1 OVERALL PASS"
