# try_tanuq.ps1 - Disposable TANUQ demo (real governed pipeline, no fake output).
# Creates a temporary workspace, walks proposal -> risk -> approval ->
# governed mutation -> verification -> evidence, then cleans itself up.
# Exit 0 + OVERALL PASS only if every governance step really happened.
#
# Usage:  powershell -ExecutionPolicy Bypass -File site\try\try_tanuq.ps1 [-KeepWorkspace]

param([switch]$KeepWorkspace)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
# ensure PowerShell pipes stdin to native programs as UTF-8 (no BOM)
$OutputEncoding = New-Object System.Text.UTF8Encoding $false

function Invoke-Tanuq {
    param([string[]]$CliArgs)
    $out = & python -m tanuq @CliArgs 2>&1 | Out-String
    return @{ ExitCode = $LASTEXITCODE; Out = "$out" }
}

function Invoke-TanuqStdin {
    param([string[]]$CliArgs, [string]$StdinData)
    $out = $StdinData | & python -m tanuq @CliArgs 2>&1 | Out-String
    return @{ ExitCode = $LASTEXITCODE; Out = "$out" }
}

# Repo root = two levels above this script (site/try/)
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $RepoRoot

Write-Host "============================================="
Write-Host " TRY TANUQ - disposable governed demo"
Write-Host "============================================="
Write-Host "Runs locally: real TANUQ pipeline, test files only."

# 1. Disposable workspace
$Workspace = Join-Path ([System.IO.Path]::GetTempPath()) ("tanuq-try-" + [Guid]::NewGuid().ToString("N").Substring(0,8))
New-Item -ItemType Directory -Path $Workspace | Out-Null
Write-Host "Workspace: $Workspace"

function Cleanup {
    if (-not $KeepWorkspace) {
        if (Test-Path $Workspace) {
            Remove-Item -Recurse -Force $Workspace
            Write-Host "Cleanup: disposable workspace removed."
        }
    } else {
        Write-Host "Workspace kept for inspection: $Workspace"
    }
}

# 2. Sample file the agent will change
$Target = Join-Path $Workspace "demo.txt"
[System.IO.File]::WriteAllText($Target, "hello", (New-Object System.Text.UTF8Encoding $false))

# 3. Init governed workspace
Write-Host "`n--- STEP 1: init (governed workspace) ---"
$r = Invoke-Tanuq @("init", "--workspace", $Workspace, "--yes")
Write-Host $r.Out
if ($r.ExitCode -ne 0 -or $r.Out -notmatch "Tanuq initialized") { Cleanup; Write-Error "init failed"; exit 1 }

# 4. LOW-risk proposal -> PROPOSED (applies on execute)
Write-Host "`n--- STEP 2: LOW-risk proposal (expect PROPOSED) ---"
$lowPayload = @{
    path        = $Target
    action      = "modify"
    reason      = "try demo: low-risk edit"
    old_content = "hello"
    new_content = "hello governed by Tanuq"
} | ConvertTo-Json
$r = Invoke-TanuqStdin @("propose", "--workspace", $Workspace, "--stdin-json", "--json") $lowPayload
if ($r.ExitCode -ne 0 -or $r.Out -notmatch '"state": "PROPOSED"') { Cleanup; Write-Error "LOW proposal failed"; exit 1 }
Write-Host "PROPOSED (LOW) - ok"

# 5. HIGH-risk proposal -> approval gate (production-named source file)
Write-Host "`n--- STEP 3: HIGH-risk proposal (expect APPROVAL REQUIRED) ---"
$HighTarget = Join-Path $Workspace "deploy_demo.py"
[System.IO.File]::WriteAllText($HighTarget, "def deploy(): return `"ok`"", (New-Object System.Text.UTF8Encoding $false))
$highPayload = @{
    path        = $HighTarget
    action      = "modify"
    reason      = "try demo: risky edit"
    old_content = "def deploy(): return `"ok`""
    new_content = "def deploy(): return `"governed by Tanuq`""
} | ConvertTo-Json
$r = Invoke-TanuqStdin @("propose", "--workspace", $Workspace, "--stdin-json", "--json") $highPayload
if ($r.ExitCode -ne 0 -or $r.Out -notmatch "APPROVAL_REQUIRED") { Cleanup; Write-Error "HIGH proposal failed"; exit 1 }
Write-Host "APPROVAL_REQUIRED (HIGH) - ok"

# 6. Human approval (single-use, fingerprint-bound)
Write-Host "`n--- STEP 4: approve (single-use, fingerprint-bound) ---"
$r = Invoke-Tanuq @("approve", "--workspace", $Workspace)
if ($r.ExitCode -ne 0 -or $r.Out -notmatch "APPROVED") { Cleanup; Write-Error "approve failed"; exit 1 }
Write-Host "APPROVED - ok"

# 7. Execute everything pending through the governed pipeline
Write-Host "`n--- STEP 5: execute (governed mutation + verification) ---"
$r = Invoke-Tanuq @("execute", "--workspace", $Workspace, "--all")
Write-Host $r.Out
if ($r.ExitCode -ne 0 -or $r.Out -notmatch "terminal state: VERIFIED") { Cleanup; Write-Error "execute failed"; exit 1 }
if ($r.Out -notmatch "Verification passed: True") { Write-Error "verification did not pass"; Cleanup; exit 1 }
Write-Host "VERIFIED - ok"

# 8. Single-use binding: nothing left pending to execute
Write-Host "`n--- STEP 6: single-use binding check ---"
$r = Invoke-Tanuq @("execute", "--workspace", $Workspace, "--all")
if ($r.Out -notmatch "No pending proposals" -and $r.ExitCode -ne 0) { Cleanup; Write-Error "replay protection missing"; exit 1 }
Write-Host "SINGLE-USE BINDING - ok"

# 9. Verify evidence chain
Write-Host "`n--- STEP 7: verify (tamper-evident evidence) ---"
$r = Invoke-Tanuq @("verify", "--workspace", $Workspace)
Write-Host $r.Out
if ($r.Out -notmatch "Evidence chain:\s+VALID") { Cleanup; Write-Error "evidence chain not VALID"; exit 1 }
if ($r.Out -notmatch "Anchor:\s+ACTIVE") { Cleanup; Write-Error "anchor not ACTIVE"; exit 1 }

# 10. Evidence summary
Write-Host "`n--- STEP 8: history (read-only evidence) ---"
$r = Invoke-Tanuq @("history", "--workspace", $Workspace)
if ($r.ExitCode -ne 0 -or $r.Out -notmatch "VERIFIED") { Cleanup; Write-Error "history failed"; exit 1 }
Write-Host "EVIDENCE - ok"

Write-Host ""
Write-Host "============================================="
Write-Host " OVERALL PASS"
Write-Host "============================================="
Write-Host "Governed demo finished: proposal -> risk -> approval ->"
Write-Host "governed mutation -> verification -> evidence."
Cleanup
exit 0
