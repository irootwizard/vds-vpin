# Build distributable release into repo-root release/ (portable bundle has no docs).
#
# Usage (repo root):
#   .\scripts\build-release.ps1
#   .\scripts\build-release.ps1 -SkipTauri -SkipRust

param(
    [switch]$SkipTauri,
    [switch]$SkipRust,
    [string]$Version = "0.1.0",
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false

function Write-Utf8File {
    param([string]$Path, [string]$Content)
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Read-Utf8Json {
    param([string]$Path)
    $raw = [System.IO.File]::ReadAllText($Path, $utf8NoBom)
    return $raw | ConvertFrom-Json
}

function Test-ReleaseDocPath {
    param([string]$RelativePath)
    $norm = ($RelativePath -replace '\\', '/').ToLowerInvariant()
    if ($norm -match '(^|/)(docs|doc|\.cursor)(/|$)') { return $true }
    if ($norm -match '\.(md|markdown|rst|adoc|pdf|html|htm)$') { return $true }
    if ($norm -match '(^|/)(readme|changelog|license)(\.|$)') { return $true }
    return $false
}

function Assert-NotDocFile {
    param([string]$Label, [string]$RelativePath)
    if (Test-ReleaseDocPath -RelativePath $RelativePath) {
        Write-Host "[ERROR] doc path blocked from release: $Label ($RelativePath)" -ForegroundColor Red
        exit 1
    }
}

$ROOT = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "lib\vpin-env.ps1")

$manifestPath = Join-Path $ROOT "config\runtime-artifacts.manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath)) {
    Write-Host "[ERROR] missing manifest: $manifestPath" -ForegroundColor Red
    exit 1
}
$manifest = Read-Utf8Json -Path $manifestPath

$releaseRoot = Join-Path $ROOT "release"
if (-not $OutDir) {
    $OutDir = Join-Path $releaseRoot "vpin-console_${Version}_win64"
}
$OutDir = [System.IO.Path]::GetFullPath($OutDir)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  vPIN Release Build v$Version" -ForegroundColor Cyan
Write-Host "  Output: $OutDir" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

if (-not $SkipRust) {
    $buildRust = Join-Path $PSScriptRoot "build-rust-ahe.ps1"
    if (Test-Path -LiteralPath $buildRust) {
        & $buildRust -Profile release
    } else {
        Write-Host "[WARN] build-rust-ahe.ps1 missing, skipping Rust build" -ForegroundColor Yellow
    }
}

$consoleDir = Get-VpinConsoleDir -RepoRoot $ROOT
if (-not $SkipTauri) {
    Write-Host "`n[Tauri] npm run tauri build ..." -ForegroundColor Cyan
    Push-Location -LiteralPath $consoleDir
    npm run tauri build
    Pop-Location
}

Write-Host "`n[Pack] assembling release tree ..." -ForegroundColor Cyan
Get-Process ahe-server -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
if (Test-Path -LiteralPath $OutDir) {
    Remove-Item -LiteralPath $OutDir -Recurse -Force
}
foreach ($d in @("bin", "config", "data\weights", "data\bsgs", "data\proof", "data\cp-snark\artifacts\A", "installer", "model_training\data\MNIST\raw")) {
    New-Item -ItemType Directory -Path (Join-Path $OutDir $d) -Force | Out-Null
}

$cli = Get-AheCliBin -RepoRoot $ROOT
$srv = Get-AheServerBin -RepoRoot $ROOT
Copy-Item -LiteralPath $cli -Destination (Join-Path $OutDir "bin\ahe-cli.exe") -Force
Copy-Item -LiteralPath $srv -Destination (Join-Path $OutDir "bin\ahe-server.exe") -Force

$cpSnark = Join-Path $ROOT "src\proof_generation\vPIN_proof_generation\target\release\cp-snark-full.exe"
$cpSnarkAlt = Join-Path $ROOT "src\cp-snark-full\target\release\cp-snark-full.exe"
if (Test-Path -LiteralPath $cpSnark) {
    Copy-Item -LiteralPath $cpSnark -Destination (Join-Path $OutDir "bin\cp-snark-full.exe") -Force
} elseif (Test-Path -LiteralPath $cpSnarkAlt) {
    Copy-Item -LiteralPath $cpSnarkAlt -Destination (Join-Path $OutDir "bin\cp-snark-full.exe") -Force
} else {
    Write-Host "[ERROR] cp-snark-full.exe not built — required for computation proof in release" -ForegroundColor Red
    Write-Host "  Build: cd src\cp-snark-full && cargo build --release" -ForegroundColor Yellow
    exit 1
}

Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $OutDir "config\runtime-artifacts.manifest.json") -Force

$catalogPath = Join-Path $ROOT "config\datasets-catalog.json"
if (-not (Test-Path -LiteralPath $catalogPath)) {
    Write-Host "[ERROR] missing datasets catalog: $catalogPath" -ForegroundColor Red
    exit 1
}
Copy-Item -LiteralPath $catalogPath -Destination (Join-Path $OutDir "config\datasets-catalog.json") -Force

$proofRegPath = Join-Path $ROOT "config\proof-registry.json"
if (-not (Test-Path -LiteralPath $proofRegPath)) {
    Write-Host "[ERROR] missing proof registry: $proofRegPath" -ForegroundColor Red
    exit 1
}
Copy-Item -LiteralPath $proofRegPath -Destination (Join-Path $OutDir "config\proof-registry.json") -Force
New-Item -ItemType Directory -Path (Join-Path $OutDir "data\cp-snark\artifacts\A") -Force | Out-Null

foreach ($item in $manifest.bundled) {
    $relSrc = ($item.source -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    $relDest = ($item.dest -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    $srcPath = Join-Path $ROOT $relSrc
    $destPath = Join-Path $OutDir $relDest
    $itemType = if ($item.type) { $item.type } else { "dir" }

    if ($itemType -eq "file") {
        if (-not (Test-Path -LiteralPath $srcPath)) {
            Write-Host "[ERROR] missing bundled file: $srcPath" -ForegroundColor Red
            exit 1
        }
        $destDir = Split-Path -Parent $destPath
        if (-not (Test-Path -LiteralPath $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }
        Write-Host "  copy file -> $relDest" -ForegroundColor Green
        Copy-Item -LiteralPath $srcPath -Destination $destPath -Force
        continue
    }

    if ($itemType -eq "dir-all-recursive") {
        if (-not (Test-Path -LiteralPath $srcPath)) {
            Write-Host "[ERROR] missing bundled dir: $srcPath" -ForegroundColor Red
            exit 1
        }
        New-Item -ItemType Directory -Path $destPath -Force | Out-Null
        $count = 0
        Get-ChildItem -LiteralPath $srcPath -Recurse -File | ForEach-Object {
            $rel = $_.FullName.Substring($srcPath.Length + 1)
            Assert-NotDocFile -Label $_.Name -RelativePath $rel
            $target = Join-Path $destPath $rel
            $parent = Split-Path -Parent $target
            if (-not (Test-Path -LiteralPath $parent)) {
                New-Item -ItemType Directory -Path $parent -Force | Out-Null
            }
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
            $count++
        }
        Write-Host "  copy dir-all-recursive -> $relDest ($count files)" -ForegroundColor Green
        continue
    }

    if ($itemType -eq "dir-all") {
        if (-not (Test-Path -LiteralPath $srcPath)) {
            Write-Host "[ERROR] missing bundled dir: $srcPath" -ForegroundColor Red
            exit 1
        }
        New-Item -ItemType Directory -Path $destPath -Force | Out-Null
        $count = 0
        Get-ChildItem -LiteralPath $srcPath -File | ForEach-Object {
            Assert-NotDocFile -Label $_.Name -RelativePath $_.Name
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $destPath $_.Name) -Force
            $count++
        }
        Write-Host "  copy dir-all -> $relDest ($count files)" -ForegroundColor Green
        continue
    }

    if (-not (Test-Path -LiteralPath $srcPath)) {
        Write-Host "[ERROR] missing bundled dir: $srcPath" -ForegroundColor Red
        exit 1
    }
    New-Item -ItemType Directory -Path $destPath -Force | Out-Null
    foreach ($file in $item.files) {
        Assert-NotDocFile -Label $file -RelativePath $file
        $src = Join-Path $srcPath $file
        if (-not (Test-Path -LiteralPath $src)) {
            Write-Host "[ERROR] missing file: $src" -ForegroundColor Red
            exit 1
        }
        Copy-Item -LiteralPath $src -Destination (Join-Path $destPath $file) -Force
    }
    if ($item.model_id) {
        Write-Host "  weights/$($item.model_id) ($($item.files.Count) files)" -ForegroundColor Green
    }
}

$regModels = @()
foreach ($item in $manifest.bundled) {
    if ($item.type -ne "dir" -or -not $item.model_id) { continue }
    $srcDir = Join-Path $ROOT (($item.source -replace '/', [System.IO.Path]::DirectorySeparatorChar))
    $snippetPath = Join-Path $srcDir "registry_snippet.json"
    if (-not (Test-Path -LiteralPath $snippetPath)) { continue }
    $entry = Read-Utf8Json -Path $snippetPath
    $entry | Add-Member -NotePropertyName weights_dir -NotePropertyValue ($item.dest -replace '\\', '/') -Force
    $entry | Add-Member -NotePropertyName deployable -NotePropertyValue $true -Force
    $entry | Add-Member -NotePropertyName message -NotePropertyValue "发布包内置 Network A 权重，Rust AHE 推理" -Force
    $regModels += $entry
}
$regJson = (@{ models = $regModels } | ConvertTo-Json -Depth 8 -Compress:$false)
Write-Utf8File -Path (Join-Path $OutDir "config\models-registry.json") -Content $regJson

$baselinePath = Join-Path $ROOT "config\release-baseline.manifest.json"
if (-not (Test-Path -LiteralPath $baselinePath)) {
    Write-Host "[ERROR] missing release baseline: $baselinePath" -ForegroundColor Red
    exit 1
}
Copy-Item -LiteralPath $baselinePath -Destination (Join-Path $OutDir "config\release-baseline.manifest.json") -Force

if (-not $SkipTauri) {
    $tauriRelease = Join-Path $consoleDir "src-tauri\target\release"
    $exe = Join-Path $tauriRelease "vpin-console.exe"
    if (Test-Path -LiteralPath $exe) {
        Copy-Item -LiteralPath $exe -Destination (Join-Path $OutDir "vpin-console.exe") -Force
    }
    $nsis = Get-ChildItem (Join-Path $tauriRelease "bundle\nsis\*.exe") -ErrorAction SilentlyContinue | Select-Object -First 1
    $msi = Get-ChildItem (Join-Path $tauriRelease "bundle\msi\*.msi") -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($nsis) {
        Copy-Item -LiteralPath $nsis.FullName -Destination (Join-Path $OutDir "installer\$($nsis.Name)") -Force
    }
    if ($msi) {
        Copy-Item -LiteralPath $msi.FullName -Destination (Join-Path $OutDir "installer\$($msi.Name)") -Force
    }
} else {
    $cachedExe = Join-Path $consoleDir "src-tauri\target\release\vpin-console.exe"
    $tauriBundle = Join-Path $consoleDir "src-tauri\target\release\bundle"
    if (-not (Test-Path -LiteralPath $tauriBundle)) {
        Write-Host "[ERROR] SkipTauri but no prior 'npm run tauri build' — exe would open localhost:1420" -ForegroundColor Red
        Write-Host "  Run: cd vpin-console && npm run tauri build" -ForegroundColor Yellow
        exit 1
    }
    if (Test-Path -LiteralPath $cachedExe) {
        Copy-Item -LiteralPath $cachedExe -Destination (Join-Path $OutDir "vpin-console.exe") -Force
        Write-Host "  reused tauri-built vpin-console.exe" -ForegroundColor Yellow
    } else {
        Write-Host "[ERROR] missing vpin-console.exe after tauri build" -ForegroundColor Red
        exit 1
    }
    $nsis = Get-ChildItem (Join-Path $tauriBundle "nsis\*.exe") -ErrorAction SilentlyContinue | Select-Object -First 1
    $msi = Get-ChildItem (Join-Path $tauriBundle "msi\*.msi") -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($nsis) { Copy-Item -LiteralPath $nsis.FullName -Destination (Join-Path $OutDir "installer\$($nsis.Name)") -Force }
    if ($msi) { Copy-Item -LiteralPath $msi.FullName -Destination (Join-Path $OutDir "installer\$($msi.Name)") -Force }
}

$startScript = @'
# Launch vPIN Console (release bundle). Sets paths for weights, BSGS, MNIST.
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$env:VPIN_REPO_ROOT = $Root
$env:VPIN_BSGS_TABLE = Join-Path $Root "data\bsgs\table.bin"
$env:VPIN_WEIGHTS_DIR = Join-Path $Root "data\weights\cnn-mnist-trained"
$exe = Join-Path $Root "vpin-console.exe"
$mnist = Join-Path $Root "model_training\data\MNIST\raw\t10k-images-idx3-ubyte"
if (-not (Test-Path -LiteralPath $exe)) {
    Write-Host "[ERROR] vpin-console.exe not found" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -LiteralPath $env:VPIN_BSGS_TABLE)) {
    Write-Host "[ERROR] missing data\bsgs\table.bin" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -LiteralPath $mnist)) {
    Write-Host "[ERROR] missing MNIST raw data under model_training\data\MNIST\raw" -ForegroundColor Red
    exit 1
}
function Wait-AheServerHealth {
    param([int]$Port = 8001, [int]$TimeoutSec = 45)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/v1/health" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) { return $true }
        } catch {}
        Start-Sleep -Seconds 1
    }
    return $false
}
$server = Join-Path $Root "bin\ahe-server.exe"
$aheUp = Wait-AheServerHealth -Port 8001 -TimeoutSec 2
if (-not $aheUp) {
    if (-not (Test-Path -LiteralPath $server)) {
        Write-Host "[ERROR] missing bin\ahe-server.exe" -ForegroundColor Red
        exit 1
    }
    Write-Host "[INFO] starting ahe-server on :8001 ..." -ForegroundColor Cyan
    Start-Process -FilePath $server -WorkingDirectory $Root -WindowStyle Hidden | Out-Null
    if (-not (Wait-AheServerHealth -Port 8001 -TimeoutSec 45)) {
        Write-Host "[ERROR] ahe-server did not become healthy on :8001" -ForegroundColor Red
        exit 1
    }
}
Set-Location -LiteralPath $Root
& $exe
'@
Write-Utf8File -Path (Join-Path $OutDir "start-vpin-console.ps1") -Content $startScript

$startBat = @'
@echo off
setlocal
cd /d "%~dp0"
set "VPIN_REPO_ROOT=%~dp0"
set "VPIN_BSGS_TABLE=%~dp0data\bsgs\table.bin"
set "VPIN_WEIGHTS_DIR=%~dp0data\weights\cnn-mnist-trained"
if not exist "%~dp0vpin-console.exe" (
  echo [ERROR] vpin-console.exe not found
  exit /b 1
)
if not exist "%VPIN_BSGS_TABLE%" (
  echo [ERROR] missing data\bsgs\table.bin
  exit /b 1
)
if not exist "%~dp0model_training\data\MNIST\raw\t10k-images-idx3-ubyte" (
  echo [ERROR] missing MNIST raw data
  exit /b 1
)
set "AHE_SERVER_HOST=127.0.0.1"
set "AHE_SERVER_PORT=8001"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$r=$env:VPIN_REPO_ROOT; $s=Join-Path $r 'bin\ahe-server.exe'; $ok=$false; try { $h=Invoke-WebRequest 'http://127.0.0.1:8001/api/v1/health' -UseBasicParsing -TimeoutSec 2; $ok=($h.StatusCode -eq 200) } catch {}; if (-not $ok) { if (-not (Test-Path $s)) { exit 2 }; Start-Process $s -WorkingDirectory $r -WindowStyle Hidden; for ($i=0; $i -lt 45; $i++) { Start-Sleep 1; try { $h=Invoke-WebRequest 'http://127.0.0.1:8001/api/v1/health' -UseBasicParsing -TimeoutSec 2; if ($h.StatusCode -eq 200) { exit 0 } } catch {} }; exit 1 }"
if errorlevel 1 (
  echo [ERROR] ahe-server failed to start on :8001
  exit /b 1
)
start "" "%~dp0vpin-console.exe"
'@
Write-Utf8File -Path (Join-Path $OutDir "start-vpin-console.bat") -Content $startBat

$packedExe = Join-Path $OutDir "vpin-console.exe"
if (-not (Test-Path -LiteralPath $packedExe)) {
    Write-Host "[ERROR] vpin-console.exe missing in bundle" -ForegroundColor Red
    exit 1
}

Get-ChildItem -LiteralPath $OutDir -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
    $rel = $_.FullName.Substring($OutDir.Length + 1)
    if (Test-ReleaseDocPath -RelativePath $rel) {
        Remove-Item -LiteralPath $_.FullName -Force
        Write-Host "  removed doc: $rel" -ForegroundColor Yellow
    }
}

$bundleName = Split-Path $OutDir -Leaf
$guideTemplate = Join-Path $PSScriptRoot "templates\release-guide.md"
if (-not (Test-Path -LiteralPath $guideTemplate)) {
    Write-Host "[ERROR] missing guide template: $guideTemplate" -ForegroundColor Red
    exit 1
}
$guide = [System.IO.File]::ReadAllText($guideTemplate, $utf8NoBom).Replace("{{BUNDLE_NAME}}", $bundleName)
$guidePath = Join-Path $releaseRoot "release-guide.md"
Write-Utf8File -Path $guidePath -Content $guide

Write-Host "`nDone: $OutDir" -ForegroundColor Green
Write-Host "Guide: $guidePath" -ForegroundColor Cyan
Get-ChildItem -LiteralPath $OutDir -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($OutDir.Length + 1)
    $mb = [math]::Round($_.Length / 1MB, 2)
    Write-Host ("  {0,7:N2} MB  {1}" -f $mb, $rel) -ForegroundColor Gray
}

Write-Host "`n[Verify] running check-release.ps1 ..." -ForegroundColor Cyan
$check = Join-Path $PSScriptRoot "check-release.ps1"
& $check -BundleDir $OutDir
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] release bundle failed verification" -ForegroundColor Red
    exit 1
}
