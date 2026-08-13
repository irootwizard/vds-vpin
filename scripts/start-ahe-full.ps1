# Start full AHE stack in separate windows: Python :8000, Rust :8001+:8002, Tauri :1420
# Usage (from repo root):
#   .\scripts\start-ahe-full.ps1
#   .\scripts\start-ahe-full.ps1 -SkipRust    # Python + Tauri only
#   .\scripts\start-ahe-full.ps1 -RustArkOnly  # skip EC on :8002

param(
    [switch]$SkipRust,
    [switch]$RustArkOnly
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "lib\vpin-env.ps1")

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AHE full stack (detached windows)" -ForegroundColor Cyan
Write-Host "  Repo: $ROOT" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$python = Get-VpinPython -RepoRoot $ROOT
$bsgs = Get-VpinBsgsPickle -RepoRoot $ROOT
if (-not (Test-Path $bsgs)) {
    Write-Host "ERROR: missing BSGS table.pickle — run .\scripts\generate-bsgs-pickle.ps1" -ForegroundColor Red
    exit 1
}
if (-not (Test-VpinModelWeights -RepoRoot $ROOT)) {
    Write-Host "ERROR: missing npy weights under model_training/outputs/" -ForegroundColor Red
    exit 1
}

$frontendDir = Get-VpinFrontendDir -RepoRoot $ROOT
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "INFO npm install (first run)..." -ForegroundColor Yellow
    Push-Location $frontendDir
    npm install
    Pop-Location
}

if (-not (Get-Command rustc -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: rust not found — https://rustup.rs (required for Tauri)" -ForegroundColor Red
    exit 1
}

foreach ($port in @(8000, 8001, 8002, 1420)) {
    if (Test-VpinPortListening -Port $port) {
        Write-Host "WARN port $port in use, releasing..." -ForegroundColor Yellow
        Stop-VpinPort -Port $port
    }
}

Write-Host ""
Write-Host "[1/3] Python backend :8000 ..." -ForegroundColor Cyan
$pyProc = Start-VpinPythonBackend -RepoRoot $ROOT -Detach
Write-Host "  PID $($pyProc.Id)" -ForegroundColor Green
if (-not (Wait-VpinHttpHealth -Port 8000 -TimeoutSec 60)) {
    Write-Host "ERROR: Python backend health check failed" -ForegroundColor Red
    exit 1
}

if (-not $SkipRust) {
    $server = Get-AheServerBin -RepoRoot $ROOT
    if (-not (Test-Path $server)) {
        Write-Host "WARN ahe-server not built — skipping Rust engines" -ForegroundColor Yellow
        Write-Host "  build: .\scripts\build-rust-ahe.ps1" -ForegroundColor Gray
    } else {
        Write-Host ""
        Write-Host "[2/3] Rust ahe-server :8001 ..." -ForegroundColor Cyan
        $arkProc = Start-VpinRustServer -RepoRoot $ROOT -Port 8001 -Detach
        Write-Host "  PID $($arkProc.Id)" -ForegroundColor Green
        if (-not (Wait-VpinHttpHealth -Port 8001 -TimeoutSec 90)) {
            Write-Host "ERROR: Rust server :8001 health check failed" -ForegroundColor Red
            exit 1
        }
        if (-not $RustArkOnly) {
            Write-Host "       Rust ahe-server :8002 ..." -ForegroundColor Cyan
            $ecProc = Start-VpinRustServer -RepoRoot $ROOT -Port 8002 -Detach
            Write-Host "  PID $($ecProc.Id)" -ForegroundColor Green
            if (-not (Wait-VpinHttpHealth -Port 8002 -TimeoutSec 90)) {
                Write-Host "ERROR: Rust server :8002 health check failed" -ForegroundColor Red
                exit 1
            }
        }
    }
} else {
    Write-Host ""
    Write-Host "[2/3] Rust engines skipped (-SkipRust)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[3/3] Tauri dev :1420 ..." -ForegroundColor Cyan
$tauriCmd = New-VpinProcessCommand -FilePath "npm" -ArgumentList @("run", "tauri", "dev") `
    -WorkingDirectory $frontendDir
$tauriProc = Start-Process powershell -ArgumentList @("-NoExit", "-Command", $tauriCmd) `
    -PassThru -WindowStyle Normal
Write-Host "  PID $($tauriProc.Id)" -ForegroundColor Green

Write-Host ""
Write-Host "Stack started (each service in its own window)." -ForegroundColor Green
Write-Host "  Python REST/WS : http://127.0.0.1:8000" -ForegroundColor White
if (-not $SkipRust) {
    Write-Host "  Rust Ark       : http://127.0.0.1:8001" -ForegroundColor White
    if (-not $RustArkOnly) {
        Write-Host "  Rust EC        : http://127.0.0.1:8002" -ForegroundColor White
    }
}
Write-Host "  Tauri UI       : http://127.0.0.1:1420 (dev server)" -ForegroundColor White
Write-Host "  Page           : /demo/ahe?model=cnn-mnist-trained" -ForegroundColor White
Write-Host ""
Write-Host "Stop: Ctrl+C in each window, or:" -ForegroundColor Gray
Write-Host "  Get-Process ahe-server -EA SilentlyContinue | Stop-Process -Force" -ForegroundColor Gray
