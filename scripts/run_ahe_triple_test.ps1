# Triple-route AHE test: Python :8000 / Rust ark :8001 / Rust ec :8002
# Usage: .\scripts\run_ahe_triple_test.ps1 [-Limit 10] [-SkipPython]

param(
    [int]$Limit = 10,
    [switch]$SkipPython
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "lib\vpin-env.ps1")

$client = Get-VpinClientRoot -RepoRoot $ROOT
$backend = Get-VpinBackendRoot -RepoRoot $ROOT
$python = Get-VpinPython -RepoRoot $ROOT
$cli = Get-AheCliBin -ClientRoot $client
$server = Get-AheServerBin -BackendRoot $backend
$bsgs = Get-VpinBsgsBin -RepoRoot $ROOT
$baseline = Join-Path $client "tests\fixtures\network_a_baseline.json"

Set-VpinDefaultEnv -RepoRoot $ROOT
$env:VPIN_BSGS_TABLE = $bsgs
$env:AHE_SERVER_HOST = "127.0.0.1"

if (-not (Test-Path $cli)) { throw "ahe-cli missing — scripts\build-rust-ahe.ps1" }
if (-not (Test-Path $server)) { throw "ahe-server missing — scripts\build-rust-ahe.ps1" }
if (-not (Test-Path $bsgs)) { throw "table.bin missing — docs/环境配置与手动步骤.md §3.2" }

function Stop-Server($proc) {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
}

function Run-RustRoute($name, $backendFlag, $port) {
    Stop-VpinPort -Port $port
    $env:AHE_SERVER_PORT = "$port"
    $srv = Start-Process -FilePath $server -WorkingDirectory $backend -PassThru -WindowStyle Hidden
    try {
        if (-not (Wait-VpinHttpHealth -Port $port -TimeoutSec 90)) { throw "server :$port unhealthy" }
        Write-Host "`n=== Rust $name single ===" -ForegroundColor Cyan
        & $cli infer --mnist-index 0 --crypto-backend $backendFlag --timing 2>&1 | Write-Host
        Write-Host "`n=== Rust $name batch (limit=$Limit) ===" -ForegroundColor Cyan
        & $cli eval-mnist-ahe --limit $Limit --concurrency 2 --progress --crypto-backend $backendFlag 2>&1 | Write-Host
    } finally {
        Stop-Server $srv
    }
}

Write-Host "Repo:   $ROOT"
Write-Host "Client: $client"
Write-Host "BSGS:   $bsgs"
Write-Host "Limit:  $Limit"

Run-RustRoute "ark" "ark" 8001
Run-RustRoute "ec" "ec" 8002

if (-not $SkipPython) {
    Stop-VpinPort -Port 8000
    $pySrv = Start-Process -FilePath $python -ArgumentList @("-m", "vpin_backend.main") `
        -WorkingDirectory $backend -PassThru -WindowStyle Hidden
    try {
        if (-not (Wait-VpinHttpHealth -Port 8000 -TimeoutSec 90)) { throw "python backend unhealthy" }
        Write-Host "`n=== Python smoke ===" -ForegroundColor Cyan
        & $python (Join-Path $ROOT "scripts\ahe_e2e_smoke.py") --model cnn-mnist-trained --mnist-index 0 --json
        if ($LASTEXITCODE -ne 0) { throw "ahe_e2e_smoke failed" }
        Write-Host "`n=== Python batch ===" -ForegroundColor Cyan
        Push-Location $ROOT
        & $python -m vpin_client.cli eval-mnist-ahe --limit $Limit --concurrency 2 --progress `
            --model cnn-mnist-trained
        Pop-Location
        if ($LASTEXITCODE -ne 0) { throw "eval-mnist-ahe failed" }
    } finally {
        Stop-Server $pySrv
    }
}

Write-Host "`n=== Triple test done ===" -ForegroundColor Green
if (Test-Path $baseline) { Write-Host "Baseline: $baseline" -ForegroundColor Gray }
