# Pull large runtime artifacts (table.bin / table.pickle) from VPIN_ARTIFACTS_BASE_URL.
# Usage (repo root):
#   $env:VPIN_ARTIFACTS_BASE_URL = "https://your-cdn/vpin-artifacts/v0.1.0"
#   .\scripts\pull-runtime-artifacts.ps1
#   .\scripts\pull-runtime-artifacts.ps1 -RustOnly
#   .\scripts\pull-runtime-artifacts.ps1 -Json

param(
    [switch]$RustOnly,
    [switch]$PythonOnly,
    [switch]$Force,
    [switch]$Json,
    [string[]]$Id
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "lib\vpin-env.ps1")

$python = Get-VpinPython -RepoRoot $ROOT
$args = @("-m", "vpin_client.bootstrap.artifacts", "--ensure")
if ($RustOnly) { $args += "--rust-only" }
if ($PythonOnly) { $args += "--python-only" }
if ($Force) { $args += "--force" }
if ($Json) { $args += "--json" }
foreach ($one in $Id) { $args += @("--id", $one) }

if (-not $env:VPIN_ARTIFACTS_BASE_URL) {
    Write-Host "[WARN] VPIN_ARTIFACTS_BASE_URL 未设置 — 仅检查本地 bundled 权重，不拉取 BSGS 表" -ForegroundColor Yellow
    Write-Host "  示例: `$env:VPIN_ARTIFACTS_BASE_URL = 'https://your-cdn/vpin-artifacts/v0.1.0'" -ForegroundColor Gray
}

Push-Location $ROOT
& $python @args
$code = $LASTEXITCODE
Pop-Location
exit $code
