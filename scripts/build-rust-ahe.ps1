# Build Rust AHE binaries (stable toolchain).
# Output:
#   vpin-client/target/release/ahe-cli(.exe)
#   vpin-backend/target/release/ahe-server(.exe)

param(
    [ValidateSet("release", "debug")]
    [string]$Profile = "release"
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "lib\vpin-env.ps1")

if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] cargo not found - install rustup: https://rustup.rs" -ForegroundColor Red
    exit 1
}

Write-Host "Rust AHE 编译 ($Profile) ..." -ForegroundColor Cyan
Write-Host "  工具链: stable（vpin-client / vpin-backend/rust-toolchain.toml）" -ForegroundColor Gray

$client = Get-VpinClientRoot -RepoRoot $ROOT
$backend = Get-VpinBackendRoot -RepoRoot $ROOT

Push-Location $client
Write-Host "`n[1/2] cargo build -p ahe-cli --profile $Profile" -ForegroundColor Cyan
cargo build -p ahe-cli --profile $Profile
Pop-Location

Push-Location $backend
Write-Host "`n[2/2] cargo build -p ahe-server --profile $Profile" -ForegroundColor Cyan
cargo build -p ahe-server --profile $Profile
Pop-Location

$cli = Get-AheCliBin -RepoRoot $ROOT
$srv = Get-AheServerBin -RepoRoot $ROOT
Write-Host "`n完成:" -ForegroundColor Green
Write-Host "  ahe-cli:    $cli" -ForegroundColor White
Write-Host "  ahe-server: $srv" -ForegroundColor White
Write-Host "`nCP-SNARK uses nightly-2023-06-26 - see docs/环境配置与手动步骤.md" -ForegroundColor Yellow
