# Verify release bundle for standalone Windows deployment.
# Usage:
#   .\scripts\check-release.ps1
#   .\scripts\check-release.ps1 -BundleDir release\vpin-console_0.1.0_win64
#   .\scripts\check-release.ps1 -SkipSmoke

param(
    [string]$BundleDir = "",
    [int]$TestPort = 8020,
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding $false
$ROOT = Split-Path -Parent $PSScriptRoot
if (-not $BundleDir) {
    $BundleDir = Join-Path $ROOT "release\vpin-console_0.1.0_win64"
}
$BundleDir = [System.IO.Path]::GetFullPath($BundleDir)

$fail = 0
$warn = 0
function Pass([string]$m) { Write-Host "[OK]   $m" -ForegroundColor Green }
function Fail([string]$m) { Write-Host "[FAIL] $m" -ForegroundColor Red; $script:fail++ }
function Warn([string]$m) { Write-Host "[WARN] $m" -ForegroundColor Yellow; $script:warn++ }

function Read-Utf8Json([string]$Path) {
    $raw = [System.IO.File]::ReadAllText($Path, $utf8)
    return $raw | ConvertFrom-Json
}

Write-Host "Release check: $BundleDir" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path -LiteralPath $BundleDir)) {
    Fail "Bundle not found — run .\scripts\build-release.ps1"
    exit 1
}

$baselinePath = Join-Path $BundleDir "config\release-baseline.manifest.json"
if (-not (Test-Path -LiteralPath $baselinePath)) {
    $baselinePath = Join-Path $ROOT "config\release-baseline.manifest.json"
}
if (-not (Test-Path -LiteralPath $baselinePath)) {
    Fail "Missing release-baseline.manifest.json"
    exit 1
}
$baseline = Read-Utf8Json -Path $baselinePath

Write-Host "-- Required files --" -ForegroundColor Cyan
foreach ($item in $baseline.required_files) {
    $rel = ($item.path -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    $p = Join-Path $BundleDir $rel
    $label = if ($item.label) { $item.label } else { $item.path }
    if (-not (Test-Path -LiteralPath $p)) {
        Fail "Missing $label ($rel)"
        continue
    }
    $sz = (Get-Item -LiteralPath $p).Length
    if ($item.min_mb -and ($sz / 1MB) -lt [double]$item.min_mb) {
        Fail "$label too small ($([math]::Round($sz / 1MB, 1)) MB, need $($item.min_mb) MB)"
    } else {
        Pass $label
    }
}

Write-Host "`n-- Optional files --" -ForegroundColor Cyan
foreach ($item in $baseline.optional_files) {
    $rel = ($item.path -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    $p = Join-Path $BundleDir $rel
    $label = if ($item.label) { $item.label } else { $item.path }
    if (-not (Test-Path -LiteralPath $p)) {
        Warn "Optional missing: $label"
        continue
    }
    $sz = (Get-Item -LiteralPath $p).Length
    if ($item.min_mb -and ($sz / 1MB) -lt [double]$item.min_mb) {
        Warn "$label present but small ($([math]::Round($sz / 1MB, 1)) MB)"
    } else {
        Pass "Optional: $label"
    }
}

Write-Host "`n-- Config JSON --" -ForegroundColor Cyan
$modelsPath = Join-Path $BundleDir "config\models-registry.json"
if (Test-Path -LiteralPath $modelsPath) {
    $modelsDoc = Read-Utf8Json -Path $modelsPath
    $ids = @($modelsDoc.models | ForEach-Object { $_.id })
    if ($ids -contains "cnn-mnist-trained") {
        Pass "models-registry contains cnn-mnist-trained"
    } else {
        Fail "models-registry missing cnn-mnist-trained"
    }
} else {
    Fail "models-registry.json not found"
}

$datasetsPath = Join-Path $BundleDir "config\datasets-catalog.json"
if (Test-Path -LiteralPath $datasetsPath) {
    $dsDoc = Read-Utf8Json -Path $datasetsPath
    $dsIds = @($dsDoc.local | ForEach-Object { $_.id })
    if ($dsIds -contains "mnist-test") {
        Pass "datasets-catalog contains mnist-test"
    } else {
        Fail "datasets-catalog missing mnist-test"
    }
} else {
    Fail "datasets-catalog.json not found"
}

Write-Host "`n-- Bundle hygiene --" -ForegroundColor Cyan
$docs = Get-ChildItem -LiteralPath $BundleDir -Recurse -File | Where-Object {
    $_.Extension -match '\.(md|txt|html|pdf)$'
}
if ($docs.Count -gt 0) {
    Warn "Doc-like files in bundle: $($docs.Count) (should be 0)"
} else {
    Pass "No doc files inside bundle"
}

$totalMb = [math]::Round(
    (Get-ChildItem -LiteralPath $BundleDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB,
    1
)
Pass "Bundle size: $totalMb MB"

$guide = Join-Path (Split-Path $BundleDir -Parent) "release-guide.md"
if (Test-Path -LiteralPath $guide) { Pass "release/release-guide.md" } else { Warn "Missing release/release-guide.md" }

$installer = Get-ChildItem (Join-Path $BundleDir "installer\*") -ErrorAction SilentlyContinue
if ($installer) { Pass "installer/ ($($installer.Count) files)" } else { Warn "installer/ empty — run full build-release.ps1 for NSIS/MSI" }

if ($baseline.pinned_sha256) {
    foreach ($prop in $baseline.pinned_sha256.PSObject.Properties) {
        $rel = ($prop.Name -replace '/', [System.IO.Path]::DirectorySeparatorChar)
        $p = Join-Path $BundleDir $rel
        if (-not (Test-Path -LiteralPath $p)) {
            Fail "Pinned hash file missing: $rel"
            continue
        }
        $gotSha = (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower()
        if ($gotSha -eq $prop.Value) {
            Pass "$rel sha256"
        } else {
            Fail "$rel sha256 mismatch"
        }
    }
}

Write-Host "`n-- System prerequisites (this machine) --" -ForegroundColor Cyan
foreach ($pre in $baseline.system_prerequisites) {
    if ($pre.dll) {
        $sysDir = Join-Path $env:WINDIR "System32"
        $dllPath = Join-Path $sysDir $pre.dll
        if (Test-Path -LiteralPath $dllPath) {
            Pass "$($pre.label) ($($pre.dll))"
        } else {
            Warn "$($pre.label) not found — target machine may need vc_redist.x64.exe"
        }
    } elseif ($pre.id -eq "webview2") {
        $wv = Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" -ErrorAction SilentlyContinue
        if ($wv) { Pass $pre.label } else { Warn "$($pre.label) — install if UI is blank" }
    } else {
        Pass "Noted: $($pre.label)"
    }
}

if ($fail -gt 0) {
    Write-Host "`nSummary: FAIL=$fail WARN=$warn — fix bundle before shipping" -ForegroundColor Red
    exit 1
}

if ($SkipSmoke) {
    Write-Host "`nSummary: FAIL=$fail WARN=$warn (smoke skipped)" -ForegroundColor $(if ($warn -gt 0) { "Yellow" } else { "Green" })
    exit 0
}

Write-Host "`n-- Smoke test (preprocess + infer) --" -ForegroundColor Cyan
$env:VPIN_REPO_ROOT = $BundleDir
$env:VPIN_BSGS_TABLE = Join-Path $BundleDir "data\bsgs\table.bin"
$env:VPIN_WEIGHTS_DIR = Join-Path $BundleDir "data\weights\cnn-mnist-trained"
$env:AHE_SERVER_HOST = "127.0.0.1"
$env:AHE_SERVER_PORT = "$TestPort"

$line = netstat -ano | Select-String "LISTENING" | Select-String ":$TestPort " | Select-Object -First 1
if ($line) {
    Stop-Process -Id (($line.ToString().Trim() -split '\s+')[-1]) -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

$server = Join-Path $BundleDir "bin\ahe-server.exe"
$cli = Join-Path $BundleDir "bin\ahe-cli.exe"
$proc = Start-Process -FilePath $server -WorkingDirectory $BundleDir -PassThru -WindowStyle Hidden
try {
    $ok = $false
    foreach ($i in 1..30) {
        Start-Sleep -Seconds 1
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$TestPort/api/v1/health" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) { $ok = $true; break }
        } catch {}
    }
    if (-not $ok) { Fail "ahe-server health on :$TestPort" } else { Pass "ahe-server health :$TestPort" }

    Push-Location -LiteralPath $BundleDir
    $pre = & $cli preprocess --mnist-index 0 2>&1
    if ($LASTEXITCODE -eq 0) { Pass "ahe-cli preprocess mnist-0" } else { Fail "ahe-cli preprocess"; $pre | Select-Object -Last 3 }

    $inf = & $cli infer --model cnn-mnist-trained --mnist-index 0 --crypto-backend ark 2>&1
    if ($LASTEXITCODE -eq 0 -and ($inf -match '"prediction"')) {
        Pass "ahe-cli infer mnist-0 (prediction present)"
    } else {
        Fail "ahe-cli infer"; $inf | Select-Object -Last 5
    }
    Pop-Location
} finally {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}

Write-Host "`nSummary: FAIL=$fail WARN=$warn" -ForegroundColor $(if ($fail -gt 0) { "Red" } elseif ($warn -gt 0) { "Yellow" } else { "Green" })
if ($fail -gt 0) { exit 1 }
exit 0
