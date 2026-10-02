<#
  TANUQ FREE - Windows installer builder (prototype).
  Assembles: embedded CPython 3.12 + preinstalled TANUQ (PyPI, pinned
  version) + launcher shims + license attributions, then compiles
  packaging/windows/tanuq.iss with Inno Setup (acquired locally if missing).

  Usage:
    powershell -ExecutionPolicy Bypass -File build_installer.ps1
    powershell -ExecutionPolicy Bypass -File build_installer.ps1 -TANUQVersion 0.6.0

  Outputs:
    packaging/windows/out/TANUQ-Setup-<version>.exe
    packaging/windows/out/SHA256SUMS.txt
#>
param(
    [string]$TANUQVersion = "0.6.0",
    [string]$PyEmbedVersion = "3.12.10",
    [string]$InnoVersion = "7.1.0",
    # Pinned artifact hashes (HARDENING 1). The Python embed SHA-256 is
    # taken from python.org's OWN SPDX SBOM for this exact artifact
    # (https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip.spdx.json
    # -> SPDXRef-PACKAGE-cpython checksums) and is additionally
    # re-fetched and re-verified on every build. The Inno Setup hash is
    # the GitHub release asset digest verified at first acquisition.
    [string]$PyEmbedSHA256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3",
    [string]$InnoSHA256 = "0362a383ed217d4c4239b5933866dd96d3eb2102737da92f80f6057a4b40df2f"
)
$ErrorActionPreference = "Stop"

$here  = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo  = Resolve-Path (Join-Path $here "..\..")
$work  = Join-Path $here "work"
$out   = Join-Path $here "out"
$embed = Join-Path $work "embed"

function Fail([string]$m) { Write-Host "FAIL: $m" -ForegroundColor Red; exit 1 }
function Ok([string]$m)   { Write-Host "OK:   $m" -ForegroundColor Green }

if ($repo.Path -match " ") { Fail "repo yolunda bosluk var (Inno define riski): $repo" }
New-Item -ItemType Directory -Force -Path $work, $out | Out-Null

# ---------------------------------------------------------------- STEP 1: Inno Setup
$iscc = $null
foreach ($p in @(
    "C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
    "C:\Program Files\Inno Setup 7\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    (Join-Path $work "innosetup\ISCC.exe")
)) { if (Test-Path $p) { $iscc = $p; break } }

if (-not $iscc) {
    Ok "Inno Setup bulunamadi, yerel olarak ediniliyor: $InnoVersion"
    $assetUrl = "https://github.com/jrsoftware/issrc/releases/download/is-$($InnoVersion -replace '\.','_')/innosetup-$InnoVersion-x64.exe"
    $installer = Join-Path $work "innosetup-setup.exe"
    Ok "indiriliyor: $assetUrl"
    Invoke-WebRequest -Uri $assetUrl -OutFile $installer -UseBasicParsing -TimeoutSec 180
    $got = (Get-FileHash -Algorithm SHA256 $installer).Hash.ToLower()
    # HARDENING 1: pinned expected hash is mandatory; live GitHub digest
    # (when available) must agree with the pin; mismatch = FAIL.
    $expected = $InnoSHA256.ToLower()
    try {
        $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/jrsoftware/issrc/releases/latest" -Headers @{ "User-Agent" = "tanuq-build" } -TimeoutSec 30
        $a = $rel.assets | Where-Object { $_.name -eq "innosetup-$InnoVersion-x64.exe" } | Select-Object -First 1
        if ($a -and $a.digest) {
            $apiSha = ($a.digest -replace "^sha256:", "").ToLower()
            if ($apiSha -ne $expected) { Fail "GitHub digest pini ile uyusmuyor: api=$apiSha pin=$expected (Inno surumu degismis olabilir)" }
            Ok "GitHub digest == pinned sha256 (Inno $InnoVersion)"
        } else { Write-Host "WARN: GitHub digest alinamadi; pinned sha256 yine de zorunlu" }
    } catch { Write-Host "WARN: GitHub API okunamadi ($($_.Exception.Message)); pinned sha256 yine de zorunlu" }
    if ($got -ne $expected) { Fail "Inno kurulum sha256 PINSI ILE UYUSMUYOR: got=$got pin=$expected" }
    Ok "Inno kurulum sha256 dogrulandi (pin): $got"
    $log = Join-Path $work "innosetup-install.log"
    $args1 = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /CURRENTUSER /DIR=`"$work\innosetup`" /LOG=`"$log`""
    $p1 = Start-Process -FilePath $installer -ArgumentList $args1 -Wait -PassThru
    if (-not (Test-Path (Join-Path $work "innosetup\ISCC.exe"))) {
        Write-Host "WARN: /CURRENTUSER ile olmadi (exit $($p1.ExitCode)), yeniden deneniyor..."
        $args2 = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /DIR=`"$work\innosetup`" /LOG=`"$log`""
        $p2 = Start-Process -FilePath $installer -ArgumentList $args2 -Wait -PassThru
        if (-not (Test-Path (Join-Path $work "innosetup\ISCC.exe"))) {
            Fail "ISCC edinilemedi (exit1=$($p1.ExitCode) exit2=$($p2.ExitCode)); log: $log"
        }
    }
    $iscc = Join-Path $work "innosetup\ISCC.exe"
}
Ok "ISCC: $iscc"

# ---------------------------------------------------------------- STEP 2: embedded CPython (HARDENING 1: resmi SPDX SHA-256)
$zip = Join-Path $work "python-embed.zip"
$marker = Join-Path $work "python-embed.sha256"
$embedUrl = "https://www.python.org/ftp/python/$PyEmbedVersion/python-$PyEmbedVersion-embed-amd64.zip"
$spdxUrl = "$embedUrl.spdx.json"

# 1) Resmi SHA-256: python.org'un kendi SPDX SBOM'u (birebir artifact baglantisiyla)
$official = $null
try {
    $spdx = (Invoke-WebRequest -Uri $spdxUrl -UseBasicParsing -TimeoutSec 60).Content | ConvertFrom-Json
    $pkg = $spdx.packages | Where-Object { $_.downloadLocation -eq $embedUrl } | Select-Object -First 1
    if (-not $pkg) { $pkg = $spdx.packages | Where-Object { $_.SPDXID -eq "SPDXRef-PACKAGE-cpython" } | Select-Object -First 1 }
    $c = $pkg.checksums | Where-Object { $_.algorithm -eq "SHA256" } | Select-Object -First 1
    if ($c) { $official = $c.checksumValue.ToLower() }
} catch { Write-Host "WARN: SPDX SBOM okunamadi: $($_.Exception.Message)" }
if (-not $official) { Fail "resmi SPDX SBOM'dan SHA256 cekilemedi: $spdxUrl (dogrulamasiz devam YOK)" }
Ok "resmi SPDX SHA256: $official"
if ($official -ne $PyEmbedSHA256.ToLower()) { Fail "PIN resmi SPDX ile uyusmuyor: pin=$PyEmbedSHA256 official=$official (pin guncellenmeli)" }
Ok "pinned embed hash == resmi python.org SPDX hash"

# 2) zip her kurulumda dogrulanir (mevcut olsa bile)
if (-not (Test-Path $zip)) { Ok "indiriliyor: $embedUrl"; Invoke-WebRequest -Uri $embedUrl -OutFile $zip -UseBasicParsing -TimeoutSec 180 }
$embedSha = (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLower()
if ($embedSha -ne $official) { Fail "embed zip SHA256 resmi degerle UYUSMUYOR: got=$embedSha official=$official" }
Ok "embed zip SHA256 dogrulandi (resmi SPDX ile birebir)"

# 3) cikarma + provenance isareti (dogrulanmamis eski dizin asla kullanilmaz)
$haveMarker = (Test-Path $marker) -and ((Get-Content $marker -Raw).Trim().ToLower() -eq $official)
if ((Test-Path $embed) -and $haveMarker) {
    Ok "embed python mevcut + dogrulama isareti tam (atlandi)"
} else {
    if (Test-Path $embed) { Write-Host "WARN: embed var ama isaret yok/eski -> yeniden cikariliyor"; Remove-Item -Recurse -Force $embed }
    New-Item -ItemType Directory -Force -Path $embed | Out-Null
    & tar -xf $zip -C $embed
    if ($LASTEXITCODE -ne 0) { Fail "embed zip cozulemedi (tar exit $LASTEXITCODE)" }
    [System.IO.File]::WriteAllText($marker, $official)
    Ok "embed python $PyEmbedVersion hazir + provenance isareti yazildi"
}

# ---------------------------------------------------------------- STEP 3: _pth patch (site-packages + site import)
$pthFile = Get-ChildItem $embed -Filter "python*._pth" | Select-Object -First 1
if (-not $pthFile) { Fail "_pth dosyasi bulunamadi" }
$pthContent = @"
python3$($PyEmbedVersion.Split('.')[1]).zip
.
Lib\site-packages
import site
"@
# python312.zip adini mevcut zip dosyasina gore ayarla
$stdZip = Get-ChildItem $embed -Filter "python*.zip" | Select-Object -First 1
$pthContent = $pthContent -replace "^python\d+\d+\.zip$", $stdZip.Name
[System.IO.File]::WriteAllText($pthFile.FullName, ($pthContent -replace "`r?`n", "`r`n"))
Ok "_pth yamalandi -> $($pthFile.Name) (Lib\site-packages + import site)"

# ---------------------------------------------------------------- STEP 4: install TANUQ into embedded env
$sp = Join-Path $embed "Lib\site-packages"
New-Item -ItemType Directory -Force -Path $sp | Out-Null
Ok "TANUQ $TANUQVersion + bagimliliklar site-packages'a kuruluyor (pip --target)..."
& python -m pip install --disable-pip-version-check --no-warn-script-location --target "$sp" "event-sourced-ai-runtime==$TANUQVersion" | Select-Object -Last 5
if ($LASTEXITCODE -ne 0) { Fail "pip --target kurulumu basarisiz (exit $LASTEXITCODE)" }

# launcher shims
Copy-Item (Join-Path $here "tanuq.cmd") $embed -Force
Copy-Item (Join-Path $here "TANUQ-UI.cmd") $embed -Force
Ok "launcher shimleri kopyalandi (tanuq.cmd, TANUQ-UI.cmd)"

# ---------------------------------------------------------------- STEP 5: license attributions
$licDir = Join-Path $embed "licenses"
New-Item -ItemType Directory -Force -Path $licDir | Out-Null
# 5a. CPython (PSF) license
$psf = $null
$cand = @( (Join-Path $embed "LICENSE.txt"), (Join-Path $embed "LICENSE"), (Join-Path $work "python-embed-PSF-LICENSE.txt") )
foreach ($c in $cand) { if (Test-Path $c) { $psf = $c; break } }
if (-not $psf) {
    try {
        $pyBase = Split-Path -Parent (Split-Path -Parent (Get-Command python).Source)
        foreach ($n in @("LICENSE.txt", "LICENSE")) {
            $c = Join-Path $pyBase $n
            if (Test-Path $c) { Copy-Item $c (Join-Path $licDir "python-PSF-LICENSE.txt"); $psf = "copied"; break }
        }
    } catch { }
}
if ($psf -and $psf -ne "copied" -and $psf -like "*embed*") { Copy-Item $psf (Join-Path $licDir "python-PSF-LICENSE.txt") }
if (-not (Test-Path (Join-Path $licDir "python-PSF-LICENSE.txt"))) {
    # son care: resmi PSF metni
    try {
        Invoke-WebRequest -Uri "https://raw.githubusercontent.com/python/cpython/$PyEmbedVersion/LICENSE.txt" -OutFile (Join-Path $licDir "python-PSF-LICENSE.txt") -UseBasicParsing -TimeoutSec 60
        Ok "PSF LICENSE resmi kaynaktan alindi (cpython $PyEmbedVersion)"
    } catch { Write-Host "WARN: PSF LICENSE alinamadi: $($_.Exception.Message)" }
} else { Ok "PSF LICENSE hazir" }

# 5b. dependency license files (dist-info/licenses ...)
$count = 0
Get-ChildItem $sp -Directory -Filter "*.dist-info" | ForEach-Object {
    $li = Join-Path $_.FullName "licenses"
    if (Test-Path $li) {
        $dest = Join-Path $licDir $_.Name
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        Copy-Item (Join-Path $li "*") $dest -Recurse -Force
        $count++
    }
}
# 5c. attribution index
$lines = @("TANUQ FREE $TANUQVersion - third-party license attributions", "", "Generated by build_installer.ps1. Each folder below contains", "the license files shipped by the corresponding distribution.", "")
Get-ChildItem $licDir -Directory | Sort-Object Name | ForEach-Object { $lines += $_.Name }
$lines += ""
$lines += "CPython (embedded interpreter) is licensed under the PSF License, see python-PSF-LICENSE.txt."
[System.IO.File]::WriteAllLines((Join-Path $licDir "THIRD_PARTY_LICENSES.txt"), $lines)
Ok "lisans atiflari: $count bagimlik lisans klasoru + THIRD_PARTY_LICENSES.txt"

# ---------------------------------------------------------------- STEP 6: version / match verification (sanitized PATH)
function Invoke-Sanitized([string]$exe, [string]$arguments) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe
    $psi.Arguments = $arguments
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.WorkingDirectory = $embed
    $psi.EnvironmentVariables["PATH"] = "$env:SystemRoot\System32"
    $psi.EnvironmentVariables.Remove("PYTHONHOME")
    $psi.EnvironmentVariables.Remove("PYTHONPATH")
    $p = [System.Diagnostics.Process]::Start($psi)
    $out = $p.StandardOutput.ReadToEnd() + $p.StandardError.ReadToEnd()
    $p.WaitForExit(60000) | Out-Null
    return ,@($p.ExitCode, $out)
}

$ver = Invoke-Sanitized (Join-Path $embed "python.exe") "-c `"import importlib.metadata as m;print(m.version('event-sourced-ai-runtime'))`""
if ($ver[0] -ne 0 -or $ver[1].Trim() -ne $TANUQVersion) { Fail "site-packages surumu dogrulanamadi: exit=$($ver[0]) cikti='$($ver[1].Trim())' (beklenen $TANUQVersion)" }
Ok "site-packages surum dogrulandi: event-sourced-ai-runtime==$TANUQVersion"

$cmdShim = Join-Path $embed "tanuq.cmd"
$r = Invoke-Sanitized "$env:ComSpec" "/c `"`"$cmdShim`" --version`""
if ($r[0] -ne 0 -or $r[1] -notmatch "Tanuq 0\.6\.0") { Fail "tanuq.cmd --version (PATH-sanitized) basarisiz: exit=$($r[0]) cikti='$($r[1].Trim())'" }
Ok "tanuq.cmd --version (PATH yalnizca System32) -> $($r[1].Trim())"

# ---------------------------------------------------------------- STEP 7: compile installer
$payload = Join-Path $work "embed"
Ok "Inno Setup derleniyor..."
& $iscc "/DAppVersion=$TANUQVersion" "/DPayloadDir=$payload" "/DOutDir=$out" (Join-Path $here "tanuq.iss") | Select-Object -Last 6
if ($LASTEXITCODE -ne 0) { Fail "ISCC derlemesi basarisiz (exit $LASTEXITCODE)" }
$setup = Join-Path $out "TANUQ-Setup-$TANUQVersion.exe"
if (-not (Test-Path $setup)) { Fail "setup exe uretilmedi: $setup" }

# ---------------------------------------------------------------- STEP 8: artifact hash
$h = Get-FileHash -Algorithm SHA256 $setup
$line = "$($h.Hash.ToLower())  $(Split-Path $setup -Leaf)"
[System.IO.File]::WriteAllText((Join-Path $out "SHA256SUMS.txt"), "$line`r`n")
Ok "ARTIFACT: $setup"
Ok "SIZE:   $((Get-Item $setup).Length) bytes"
Ok "SHA256: $($h.Hash.ToLower())"
Write-Host "BUILD PASSED"
exit 0
