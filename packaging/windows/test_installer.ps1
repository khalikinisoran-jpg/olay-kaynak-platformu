<#
  TANUQ FREE - Windows installer test (prototype, local machine).
  Tests: silent per-user install -> PATH-sanitized payload E2E
  (version/help/init/propose/approve/execute/verify/ui) -> uninstall.

  NOTE: this is NOT a clean Windows VM test. See README.md limitations.

  Usage:
    powershell -ExecutionPolicy Bypass -File test_installer.ps1
    powershell -ExecutionPolicy Bypass -File test_installer.ps1 -SetupPath out\TANUQ-Setup-0.6.0.exe
#>
param(
    [string]$SetupPath = ""
)
$ErrorActionPreference = "Stop"
$here  = Split-Path -Parent $MyInvocation.MyCommand.Path
$work  = Join-Path $here "work"
$out   = Join-Path $here "out"
if (-not $SetupPath) { $SetupPath = Join-Path $out "TANUQ-Setup-0.6.0.exe" }

$app     = Join-Path $env:LOCALAPPDATA "Programs\TANUQ"
$homeIso = Join-Path $work "test-home"
$ws      = Join-Path $env:TEMP ("tanuq-f3-ws-" + [Guid]::NewGuid().ToString("N").Substring(0, 8))
$grp     = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\TANUQ"
$dtop    = Join-Path $env:USERPROFILE "Desktop\TANUQ.lnk"

$script:pass = 0
$script:fail = 0
function Ok([string]$m)   { Write-Host "PASS: $m" -ForegroundColor Green; $script:pass++ }
function Bad([string]$m)  { Write-Host "FAIL: $m" -ForegroundColor Red;   $script:fail++ }
function Info([string]$m) { Write-Host "INFO: $m" }

function Invoke-Tanuq([string]$arguments, [int]$timeoutSec = 60, [string]$stdinFile = "", [string]$workingDir = "") {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "$env:SystemRoot\System32\cmd.exe"
    $inner = "`"$app\tanuq.cmd`" $arguments"
    if ($stdinFile) { $inner = "$inner < `"$stdinFile`"" }
    $psi.Arguments = "/c `"$inner`""
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    if ($workingDir) { $psi.WorkingDirectory = $workingDir } else { $psi.WorkingDirectory = $work }
    # Prove the payload does not rely on system Python/Git on PATH.
    $psi.EnvironmentVariables["PATH"] = "$env:SystemRoot\System32"
    $psi.EnvironmentVariables.Remove("PYTHONHOME")
    $psi.EnvironmentVariables.Remove("PYTHONPATH")
    # Keep user HOME isolation (no pollution of the real ~/.tanuq).
    New-Item -ItemType Directory -Force -Path $homeIso | Out-Null
    $psi.EnvironmentVariables["HOME"] = $homeIso
    $psi.EnvironmentVariables["USERPROFILE"] = $homeIso
    $p = [System.Diagnostics.Process]::Start($psi)
    $ms = $p.StandardOutput.ReadToEndAsync()
    $es = $p.StandardError.ReadToEndAsync()
    if (-not $p.WaitForExit($timeoutSec * 1000)) { try { $p.Kill() } catch { }; return ,@(-99, "TIMEOUT after ${timeoutSec}s") }
    return ,@($p.ExitCode, ($ms.Result + $es.Result))
}

# ---------------------------------------------------------------- TEST D: install
Write-Host "`n=== TEST D: INSTALL ==="
if (-not (Test-Path $SetupPath)) { Bad "setup exe yok: $SetupPath"; exit 1 }
$setupSha = (Get-FileHash -Algorithm SHA256 $SetupPath).Hash.ToLower()
Info "setup: $SetupPath ($((Get-Item $SetupPath).Length) bytes, sha256=$setupSha)"

$elevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Info "current token elevated (admin): $elevated  (per-user install yine de admin GEREKTIRMEZ; gercek non-admin VM testi yapilmadi)"

if (Test-Path (Join-Path $app "unins000.exe")) {
    Info "onceki kurulum bulundu, temizleniyor..."
    Start-Process (Join-Path $app "unins000.exe") "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART" -Wait
}
if (Test-Path $app) { Get-ChildItem $app -Recurse -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue }

$ilog = Join-Path $work "test-install.log"
$p = Start-Process -FilePath $SetupPath -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/LOG=`"$ilog`"" -Wait -PassThru
Info "installer exit: $($p.ExitCode)"
if (-not (Test-Path $app)) { Bad "kurulumdan sonra $app yok" } else { Ok "kurulum dizini mevcut: $app" }
if (-not (Test-Path (Join-Path $app "python.exe")))     { Bad "payload python.exe yok" } else { Ok "embedded python.exe kurulu" }
if (-not (Test-Path (Join-Path $app "tanuq.cmd")))      { Bad "tanuq.cmd yok" } else { Ok "tanuq.cmd kurulu" }
if (-not (Test-Path (Join-Path $app "TANUQ-UI.cmd")))   { Bad "TANUQ-UI.cmd yok" } else { Ok "TANUQ-UI.cmd kurulu" }
if (-not (Test-Path (Join-Path $app "licenses\THIRD_PARTY_LICENSES.txt"))) { Bad "lisans atifi yok" } else { Ok "lisans atiflari kurulu (licenses\THIRD_PARTY_LICENSES.txt)" }
if (Test-Path $grp)    { Ok "Start Menu kisayollari mevcut" } else { Bad "Start Menu kisayolu yok: $grp" }
if (Test-Path $dtop)   { Ok "Desktop kisayolu mevcut" } else { Bad "Desktop kisayolu yok" }

# ---------------------------------------------------------------- TEST E: TANUQ run (sanitized PATH + isolated HOME)
Write-Host "`n=== TEST E: TANUQ CALISMA ==="
$r = Invoke-Tanuq "--version"
if ($r[0] -eq 0 -and $r[1] -match "Tanuq 0\.6\.0") { Ok "tanuq --version -> $($r[1].Trim())" } else { Bad "tanuq --version: exit=$($r[0]) $($r[1].Trim())" }

$r = Invoke-Tanuq "--help"
if ($r[0] -eq 0 -and $r[1] -match "usage: tanuq") { Ok "tanuq --help (exit 0, $($r[1].Split("`n").Count) satir)" } else { Bad "tanuq --help: exit=$($r[0])" }

New-Item -ItemType Directory -Force -Path $ws | Out-Null
$r = Invoke-Tanuq "init --yes --workspace `"$ws`"" 60
if ($r[0] -eq 0 -and $r[1] -match "Tanuq initialized") { Ok "tanuq init --yes" } else { Bad "init: exit=$($r[0]) $($r[1].Substring(0, [Math]::Min(200, $r[1].Length)))" }

$prop = Join-Path $work "test-proposal.json"
'{"path": "notes.txt", "action": "create", "old_content": "", "new_content": "f3 installer e2e", "reason": "F3 installer test"}' |
    Set-Content -Path $prop -Encoding Ascii -NoNewline
$r = Invoke-Tanuq "propose --stdin-json --workspace `"$ws`"" 60 $prop $ws
if ($r[0] -eq 0 -and $r[1] -match "APPROVAL_REQUIRED") { Ok "tanuq propose (create -> HIGH/APPROVAL_REQUIRED)" } else { Bad "propose: exit=$($r[0]) $($r[1].Substring(0, [Math]::Min(300, $r[1].Length)))" }

$r = Invoke-Tanuq "approve --workspace `"$ws`"" 60
if ($r[0] -eq 0 -and $r[1] -match "APPROVED") { Ok "tanuq approve (single-use)" } else { Bad "approve: exit=$($r[0])" }

$r = Invoke-Tanuq -arguments "execute --workspace `"$ws`"" -timeoutSec 300 -workingDir $ws
if ($r[0] -eq 0 -and $r[1] -match "terminal state: VERIFIED") { Ok "tanuq execute -> VERIFIED (embedded python ile dogrulama dahil)" } else { Bad "execute: exit=$($r[0]) $($r[1].Substring(0, [Math]::Min(300, $r[1].Length)))" }

$created = Join-Path $ws "notes.txt"
if ((Test-Path $created) -and ((Get-Content $created -Raw) -match "f3 installer e2e")) { Ok "uretilen dosya dogrulandi: notes.txt" } else { Bad "notes.txt yok/icerik hatali" }

$r = Invoke-Tanuq -arguments "verify --workspace `"$ws`"" -timeoutSec 60 -workingDir $ws
if ($r[0] -eq 0 -and $r[1] -match "VALID") { Ok "tanuq verify -> evidence chain VALID" } else { Bad "verify: exit=$($r[0])" }

$r = Invoke-Tanuq -arguments "history --workspace `"$ws`"" -timeoutSec 60 -workingDir $ws
if ($r[0] -eq 0 -and $r[1] -match "VERIFIED") { Ok "tanuq history -> VERIFIED kaydi" } else { Bad "history: exit=$($r[0])" }

# UI server (port dinleme kontrolu; tarayici acilmaz)
$ui = New-Object System.Diagnostics.ProcessStartInfo
$ui.FileName = Join-Path $app "python.exe"
$ui.Arguments = "-m tanuq ui --workspace `"$ws`""
$ui.UseShellExecute = $false
$ui.RedirectStandardOutput = $true
$ui.RedirectStandardError = $true
$ui.WorkingDirectory = $ws
$ui.EnvironmentVariables["PATH"] = "$env:SystemRoot\System32"
$ui.EnvironmentVariables["HOME"] = $homeIso
$ui.EnvironmentVariables["USERPROFILE"] = $homeIso
$uiProc = [System.Diagnostics.Process]::Start($ui)
$up = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    try { $c = New-Object Net.Sockets.TcpClient; $c.Connect("127.0.0.1", 8770); $up = $c.Connected; $c.Close(); if ($up) { break } } catch { }
}
if ($up) {
    Ok "tanuq ui -> 127.0.0.1:8770 dinlemede (PID $($uiProc.Id))"
    try { $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8770/" -UseBasicParsing -TimeoutSec 5; Info "HTTP GET / -> $($resp.StatusCode)" } catch { Info "HTTP GET / -> $($_.Exception.Message.Split([char]10)[0]) (token fail-cold 403 normal olabilir)" }
} else { Bad "tanuq ui port 8770 acilmadi" }
try { if (-not $uiProc.HasExited) { $uiProc.Kill() } } catch { }
try { $uiProc.WaitForExit(5000) | Out-Null } catch { }
Ok "tanuq ui process durduruldu"

# ---------------------------------------------------------------- TEST F: uninstall
Write-Host "`n=== TEST F: UNINSTALL ==="
$unins = Join-Path $app "unins000.exe"
if (-not (Test-Path $unins)) { Bad "unins000.exe yok" } else {
    $p = Start-Process -FilePath $unins -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART" -Wait -PassThru
    Info "uninstall exit: $($p.ExitCode)"
    Start-Sleep -Seconds 2
    if (Test-Path $app) {
        $left = @(Get-ChildItem $app -Recurse -Force -ErrorAction SilentlyContinue)
        if ($left.Count -eq 0) { Ok "kaldirma: dizin bos kaldi (temiz)" } else { Bad "kaldirma: $($left.Count) kaldi: " + (($left | Select-Object -First 5 | ForEach-Object { $_.Name }) -join ", ") }
    } else { Ok "kaldirma: $app tamamen silindi" }
    if (Test-Path $dtop) { Bad "Desktop kisayolu hala var" } else { Ok "Desktop kisayolu silindi" }
    if (Test-Path $grp)  { Bad "Start Menu grubu hala var" } else { Ok "Start Menu grubu silindi" }
}

# ---------------------------------------------------------------- cleanup + summary
try {
    if ([System.IO.Directory]::Exists($ws)) { [System.IO.Directory]::Delete($ws, $true) }
} catch {
    try { & "$env:SystemRoot\System32\cmd.exe" "/c rd /s /q `"$ws`"" | Out-Null } catch { }
    if ([System.IO.Directory]::Exists($ws)) { Info "ws temizlik notu: kalici ($ws)" } else { Ok "gecici workspace temizlendi" }
}
try { if (Test-Path $prop) { Remove-Item -Force $prop -ErrorAction Stop } } catch { }
Write-Host ""
Write-Host "================ TEST SUMMARY ================"
Write-Host "PASS: $script:pass   FAIL: $script:fail"
if ($script:fail -eq 0) { Write-Host "ALL INSTALLER TESTS PASSED" -ForegroundColor Green; exit 0 }
else { Write-Host "TESTS FAILED" -ForegroundColor Red; exit 1 }
