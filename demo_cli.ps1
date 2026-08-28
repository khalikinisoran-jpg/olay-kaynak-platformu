# demo_cli.ps1 — Reproducible Governed CLI Demo (P2.3-A)
# Real CLI path only: task -> approve --pending -> task -> replay -> history
# Exit 0 + OVERALL PASS only if all governance invariants observed.

$ErrorActionPreference = "Stop"

function Invoke-Cli {
    param([string[]]$CliArgs)
    $output = & python @CliArgs 2>&1 | Out-String
    $code = $LASTEXITCODE
    if ($null -eq $output) { $output = "" }
    return @{ ExitCode = $code; Out = $output; Err = ""; Combined = $output }
}

# Resolve repo root (script location)
$RepoRoot = $PSScriptRoot
if (-not $RepoRoot) { $RepoRoot = (Get-Location).Path }
Set-Location $RepoRoot

Write-Host "============================================"
Write-Host " GOVERNED CLI DEMO - P2.3-A (real CLI only)"
Write-Host "============================================"
Write-Host "Repo: $RepoRoot"

# A. Fresh temp workspace
$Workspace = Join-Path ([System.IO.Path]::GetTempPath()) ("demo_cli_" + [Guid]::NewGuid().ToString("N").Substring(0,8))
New-Item -ItemType Directory -Path $Workspace | Out-Null
Write-Host "Workspace: $Workspace"

# B. demo.txt exactly "hello" (no BOM, no newline) - avoids UTF-8 BOM / newline drift
$Target = Join-Path $Workspace "demo.txt"
[System.IO.File]::WriteAllText($Target, "hello", (New-Object System.Text.UTF8Encoding $false))
$actual = [System.IO.File]::ReadAllText($Target)
if ($actual -ne "hello") { Write-Error "Setup failed: demo.txt not exactly 'hello' got '$actual'"; exit 1 }
Write-Host "Created demo.txt with exact 'hello' (no newline, no BOM) length=$($actual.Length)"

$Goal = "add api_key secret to file"

# C. First HIGH-risk task - must be DENIED
Write-Host ""
Write-Host "--- STEP 1: HIGH-risk task without approval (expect DENIED) ---"
$r1 = Invoke-Cli @("agent_run.py","task","--goal",$Goal,"--workspace",$Workspace,"--file","demo.txt","--fake-analyzer")
Write-Host $r1.Out
if ($r1.ExitCode -eq 0) { Write-Error "STEP1 should be DENIED (non-zero exit) but got 0"; exit 1 }
$deniedWithoutApproval = ($r1.Out -match "Risk: HIGH") -and ($r1.Out -match "Approval required: True") -and ($r1.Out -match "Failure stage: approval") -and ($r1.Out -match "DENIED")
if (-not $deniedWithoutApproval) { Write-Error "STEP1 governance check failed: missing Risk HIGH / Approval required / Failure approval / DENIED"; exit 1 }
Write-Host "DENIED WITHOUT APPROVAL - ok"
# also ensure no mutation
$after1 = [System.IO.File]::ReadAllText($Target)
if ($after1 -ne "hello") { Write-Error "STEP1 file should remain 'hello' but is '$after1'"; exit 1 }

# Verify pending exists (exact proposal persisted)
$Pending = Join-Path (Join-Path $Workspace ".cli_platform") "pending_proposals.json"
if (-not (Test-Path $Pending)) { Write-Error "Pending file not found at $Pending"; exit 1 }
Write-Host "Pending persisted at $Pending"

# E. Approve via pending (mechanical, no manual fingerprint)
Write-Host ""
Write-Host "--- STEP 2: approve --pending (mechanical exact fingerprint) ---"
$r2 = Invoke-Cli @("agent_run.py","approve","--pending","--workspace",$Workspace)
Write-Host $r2.Out
if ($r2.ExitCode -ne 0) { Write-Error "STEP2 approve --pending failed exit $($r2.ExitCode)"; exit 1 }
$approved = ($r2.Out -match "Approval granted")
if (-not $approved) { Write-Error "STEP2 missing 'Approval granted'"; exit 1 }
Write-Host "APPROVED - ok"

# F+G. Identical task again — must be VERIFIED
Write-Host ""
Write-Host "--- STEP 3: identical HIGH-risk task after approval (expect VERIFIED) ---"
$r3 = Invoke-Cli @("agent_run.py","task","--goal",$Goal,"--workspace",$Workspace,"--file","demo.txt","--fake-analyzer")
Write-Host $r3.Out
if ($r3.ExitCode -ne 0) { Write-Error "STEP3 should be VERIFIED (exit 0) but got $($r3.ExitCode)"; exit 1 }
$verifiedAfterApproval = ($r3.Out -match "Terminal state: VERIFIED") -and ($r3.Out -match "Pipeline success: True")
if (-not $verifiedAfterApproval) { Write-Error "STEP3 missing VERIFIED / Pipeline success"; exit 1 }
Write-Host "VERIFIED AFTER APPROVAL - ok"
$after3 = [System.IO.File]::ReadAllText($Target)
if ($after3 -notmatch 'api_key') { Write-Error "STEP3 file should contain api_key but is '$after3'"; exit 1 }

# H. Replay protection - restore original and rerun identical task (must be DENIED, single-use)
Write-Host ""
Write-Host "--- STEP 4: replay protection (restore hello, rerun identical task, expect DENIED) ---"
[System.IO.File]::WriteAllText($Target, "hello", (New-Object System.Text.UTF8Encoding $false))
Write-Host "Restored demo.txt to 'hello'"
$r4 = Invoke-Cli @("agent_run.py","task","--goal",$Goal,"--workspace",$Workspace,"--file","demo.txt","--fake-analyzer")
Write-Host $r4.Out
if ($r4.ExitCode -eq 0) { Write-Error "STEP4 replay should be DENIED (non-zero) but got 0"; exit 1 }
$replayDenied = ($r4.Out -match "Failure stage: approval") -and ( ($r4.Out -match "DENIED") -or ($r4.Out -match "already consumed") -or ($r4.Out -match "required but missing") )
if (-not $replayDenied) { Write-Error "STEP4 missing replay DENIED evidence"; exit 1 }
$after4 = [System.IO.File]::ReadAllText($Target)
if ($after4 -ne "hello") { Write-Error "STEP4 file should remain 'hello' after DENIED replay but is '$after4'"; exit 1 }
Write-Host "REPLAY DENIED - ok (single-use)"

# I. History read-only
Write-Host ""
Write-Host "--- STEP 5: history --workspace (read-only) ---"
$journalBefore = $null
$journalPath = Join-Path (Join-Path $Workspace ".cli_platform") "apply_journal.jsonl"
if (Test-Path $journalPath) { $journalBefore = [System.IO.File]::ReadAllBytes($journalPath) }
$r5 = Invoke-Cli @("agent_run.py","history","--workspace",$Workspace)
Write-Host $r5.Out
if ($r5.ExitCode -ne 0) { Write-Error "history failed exit $($r5.ExitCode)"; exit 1 }
$historyOk = ($r5.Out -match "APPLY HISTORY") -and ($r5.Out -match "READ ONLY") -and ($r5.Out -match "Lifecycle:") -and ($r5.Out -match "Terminal:")
if (-not $historyOk) { Write-Error "history output missing APPLY HISTORY / READ ONLY / Lifecycle / Terminal"; exit 1 }
if (Test-Path $journalPath) {
    $journalAfter = [System.IO.File]::ReadAllBytes($journalPath)
    if ($journalBefore.Length -ne $journalAfter.Length) { Write-Error "history mutated journal"; exit 1 }
    for ($i=0; $i -lt $journalBefore.Length; $i++) { if ($journalBefore[$i] -ne $journalAfter[$i]) { Write-Error "history mutated journal bytes"; exit 1 } }
}
Write-Host "HISTORY READ-ONLY - ok"

Write-Host ""
Write-Host "============================================"
Write-Host " OVERALL PASS"
Write-Host "============================================"
Write-Host "DENIED WITHOUT APPROVAL : ok"
Write-Host "APPROVED                : ok"
Write-Host "VERIFIED AFTER APPROVAL : ok"
Write-Host "REPLAY DENIED           : ok (single-use binding)"
Write-Host "HISTORY READ-ONLY       : ok"
Write-Host "Workspace: $Workspace (kept for inspection)"
exit 0
