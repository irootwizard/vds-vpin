# MVP-AHE one-click start (Python backend + Tauri, foreground)
# Usage: .\start-ahe.ps1
# Full stack (detached windows): .\scripts\start-ahe-full.ps1
# First time: .\scripts\setup.ps1 then .\scripts\check-env.ps1

param(
    [switch]$BothRust
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ROOT "scripts\lib\vpin-env.ps1")

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MVP-AHE start" -ForegroundColor Cyan
Write-Host "  Repo: $ROOT" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$python = Get-VpinPython -RepoRoot $ROOT
$bsgs = Get-VpinBsgsPickle -RepoRoot $ROOT
if (-not (Test-Path $bsgs)) {
    Write-Host "ERROR: missing BSGS table.pickle: $bsgs" -ForegroundColor Red
    Write-Host "  run .\scripts\generate-bsgs-pickle.ps1" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-VpinModelWeights -RepoRoot $ROOT)) {
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
    & (Get-VpinPip -RepoRoot $ROOT) install -e (Join-Path $ROOT "vpin-client") | Out-Null
    & (Get-VpinPip -RepoRoot $ROOT) install -r (Join-Path $ROOT "vpin-backend\requirements.txt") torch torchvision pillow websockets | Out-Null
}

foreach ($port in @(8000, 8001, 1420)) {
    if (Test-VpinPortListening -Port $port) {
        Write-Host "WARN port $port in use, releasing..." -ForegroundColor Yellow
        Stop-VpinPort -Port $port
    }
}

Set-VpinDefaultEnv -RepoRoot $ROOT

Write-Host ""
Write-Host "[1/2] Backend http://127.0.0.1:8000 ..." -ForegroundColor Cyan
$backend = Start-VpinPythonBackend -RepoRoot $ROOT
Write-Host "  backend PID $($backend.Id)" -ForegroundColor Green
if (-not (Wait-VpinHttpHealth -Port 8000 -TimeoutSec 60)) {
    Write-Host "ERROR: backend health check failed" -ForegroundColor Red
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    exit 1
}

$server = Get-AheServerBin -RepoRoot $ROOT
if (Test-Path $server) {
    Write-Host "Starting Rust ahe-server :8001 (detached) ..." -ForegroundColor Cyan
    & (Join-Path $ROOT "scripts\start-rust-ahe.ps1") -Detach
} else {
    Write-Host "WARN ahe-server not built — run .\scripts\build-rust-ahe.ps1" -ForegroundColor Yellow
    Write-Host "  CNN 推理将不可用直至编译 ahe-server + ahe-cli" -ForegroundColor Yellow
}

if ($BothRust) {
    $server2 = Get-AheServerBin -RepoRoot $ROOT
    if (Test-Path $server2) {
        Write-Host "Starting Rust EC engine :8002 (detached) ..." -ForegroundColor Cyan
        if (-not (Test-VpinPortListening -Port 8002)) {
            Start-VpinRustServer -RepoRoot $ROOT -Port 8002 -Detach | Out-Null
            if (-not (Wait-VpinHttpHealth -Port 8002 -TimeoutSec 90)) {
                Write-Host "WARN :8002 EC engine failed health check" -ForegroundColor Yellow
            }
        }
    }
}

$frontendDir = Get-VpinFrontendDir -RepoRoot $ROOT
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
    Get-Process -Name "ahe-server" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Get-Process -Name "vpin-frontend","vpin-console" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped." -ForegroundColor Green
}

Write-Host ""
$uiLabel = if ($env:VPIN_UI -eq "legacy") { "legacy vpin-frontend" } else { "vpin-console (default)" }
Write-Host "[2/2] Tauri dev ($uiLabel) ..." -ForegroundColor Cyan
Write-Host "  backend PID $($backend.Id) logs in separate window" -ForegroundColor Gray
Write-Host "  Full stack: .\scripts\start-ahe-full.ps1" -ForegroundColor Gray
Write-Host "  Rust only:  .\scripts\start-rust-ahe.ps1 -Both -Detach" -ForegroundColor Gray
Write-Host ""

Push-Location $frontendDir
try {
    npm run tauri dev
} finally {
    Pop-Location
    Stop-VpinStack
}
