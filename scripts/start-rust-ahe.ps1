# Start Rust ahe-server instances for UI Rust engines.
# Usage (from repo root):
#   .\scripts\start-rust-ahe.ps1           # Ark on :8001
#   .\scripts\start-rust-ahe.ps1 -Both       # Ark :8001 + EC :8002
#   .\scripts\start-rust-ahe.ps1 -Both -Detach   # separate windows, exit when ready

param(
    [switch]$Both,
    [switch]$NoWait,
    [switch]$Detach
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "lib\vpin-env.ps1")

Set-VpinDefaultEnv -RepoRoot $ROOT
$server = Get-AheServerBin -RepoRoot $ROOT
$bsgs = Get-VpinBsgsBin -RepoRoot $ROOT

if (-not (Test-Path $server)) {
    Write-Host "ERROR: ahe-server not found — run scripts\build-rust-ahe.ps1" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $bsgs)) {
    Write-Host "ERROR: missing table.bin — see docs/环境配置与手动步骤.md §3.2" -ForegroundColor Red
    exit 1
}

function Start-One($port) {
    Write-Host "Starting ahe-server on port $port ..." -ForegroundColor Cyan
    if ($Detach) {
        $p = Start-VpinRustServer -RepoRoot $ROOT -Port $port -Detach
    } else {
        $p = Start-VpinRustServer -RepoRoot $ROOT -Port $port
    }
    if (-not (Wait-VpinHttpHealth -Port $port -TimeoutSec 90)) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        throw "ahe-server on port $port failed health check (timeout 90s)"
    }
    Write-Host "  PID $($p.Id) -> http://127.0.0.1:$port/api/v1/health" -ForegroundColor Green
    return $p
}

$procs = @()
$procs += Start-One 8001
if ($Both) {
    $procs += Start-One 8002
}

Write-Host ""
Write-Host "Rust server ready. UI: Rust Ark -> :8001" -ForegroundColor Green
if ($Both) {
    Write-Host "Rust EC client -> :8002 (CLI: --crypto-backend ec)" -ForegroundColor Green
}

if ($NoWait -or $Detach) { exit 0 }

Write-Host "Press Enter to stop Rust servers ..." -ForegroundColor Yellow
Read-Host | Out-Null
foreach ($p in $procs) {
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}
