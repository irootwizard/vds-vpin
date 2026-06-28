# MVP-AHE one-click start (Python backend + Tauri)
# Usage: .\start-ahe.ps1
# First time: .\scripts\setup.ps1 then .\scripts\check-env.ps1

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ROOT "scripts\lib\vpin-env.ps1")

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MVP-AHE start" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$python = Join-Path $ROOT ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "ERROR: missing .venv - run .\scripts\setup.ps1" -ForegroundColor Red
    exit 1
}

$bsgs = Get-VpinBsgsPickle -RepoRoot $ROOT
if (-not (Test-Path $bsgs)) {
    Write-Host "ERROR: missing BSGS table.pickle: $bsgs" -ForegroundColor Red
    Write-Host "  run .\scripts\generate-bsgs-pickle.ps1" -ForegroundColor Yellow
    exit 1
}

$modelRuns = @(
    "model_training\outputs\20260622_184254",
    "model_training\outputs\20260623_185935"
)
$hasWeights = $false
foreach ($run in $modelRuns) {
    $runPath = Join-Path $ROOT $run
    if ((Test-Path $runPath) -and (Get-ChildItem $runPath -Filter "*.npy" -ErrorAction SilentlyContinue).Count -gt 0) {
        $hasWeights = $true
        break
    }
}
if (-not $hasWeights) {
    Write-Host "ERROR: missing npy weights under model_training/outputs/" -ForegroundColor Red
    exit 1
}
Write-Host "OK weights (model_training/outputs/)" -ForegroundColor Green

$pyVer = & $python --version 2>&1
Write-Host "OK Python $pyVer" -ForegroundColor Green
$bsgsMb = [math]::Round((Get-Item $bsgs).Length / 1MB, 1)
Write-Host "OK BSGS table.pickle (${bsgsMb} MB)" -ForegroundColor Green

# Python package check (temp script avoids PowerShell parsing python -c multiline)
$pyCheck = Join-Path $env:TEMP "vpin_start_pkg_check.py"
@'
import importlib.util
pkgs = ["fastapi","uvicorn","ecdsa","numpy","websockets","PIL","torch","torchvision","pydantic","pydantic_settings","gmpy2"]
miss = [p for p in pkgs if importlib.util.find_spec(p.split(".")[0]) is None]
print(",".join(miss))
'@ | Set-Content -Path $pyCheck -Encoding UTF8
$missing = & $python $pyCheck 2>&1
Remove-Item $pyCheck -Force -ErrorAction SilentlyContinue
if ($missing -and $missing.ToString().Trim()) {
    Write-Host "WARN missing packages: $missing - installing..." -ForegroundColor Yellow
    & (Join-Path $ROOT ".venv\Scripts\pip.exe") install -e (Join-Path $ROOT "vpin-client") | Out-Null
    & (Join-Path $ROOT ".venv\Scripts\pip.exe") install -r (Join-Path $ROOT "vpin-backend\requirements.txt") torch torchvision pillow websockets | Out-Null
}

foreach ($port in @(8000, 1420)) {
    $line = netstat -ano | Select-String "LISTENING" | Select-String ":$port " | Select-Object -First 1
    if ($line) {
        Write-Host "WARN port $port in use, releasing..." -ForegroundColor Yellow
        $procId = ($line.ToString().Trim() -split '\s+')[-1]
        if ($procId -match '^\d+$') {
            Stop-Process -Id ([int]$procId) -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1
    }
}

Write-Host ""
Write-Host "[1/2] Backend http://127.0.0.1:8000 ..." -ForegroundColor Cyan
$backend = Start-Process -FilePath $python `
    -ArgumentList "-m", "vpin_backend.main" `
    -WorkingDirectory (Join-Path $ROOT "vpin-backend") `
    -PassThru -WindowStyle Normal
Write-Host "  backend PID $($backend.Id)" -ForegroundColor Green
Start-Sleep -Seconds 3

$frontendDir = Join-Path $ROOT "vpin_frontend\vpin-frontend"
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "INFO npm install (first run)..." -ForegroundColor Yellow
    Push-Location $frontendDir
    npm install
    Pop-Location
}

if (-not (Get-Command rustc -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: rust not found - https://rustup.rs" -ForegroundColor Red
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    exit 1
}
Write-Host "OK Rust $(rustc --version)" -ForegroundColor Green

function Stop-VpinStack {
    Write-Host "`nStopping..." -ForegroundColor Yellow
    if ($backend -and -not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
    Get-Process -Name "vpin-frontend" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped." -ForegroundColor Green
}

Write-Host ""
Write-Host "[2/2] Tauri dev (compile output in this terminal) ..." -ForegroundColor Cyan
Write-Host "  backend PID $($backend.Id) logs in separate window" -ForegroundColor Gray
Write-Host "  Rust engine: .\scripts\start-rust-ahe.ps1 -Both" -ForegroundColor Gray
Write-Host ""

Push-Location $frontendDir
try {
    npm run tauri dev
} finally {
    Pop-Location
    Stop-VpinStack
}
