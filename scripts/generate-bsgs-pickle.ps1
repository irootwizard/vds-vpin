# Generate Python BSGS table (table.pickle, ~230MB, ~30 min).
# Usage: .\scripts\generate-bsgs-pickle.ps1

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "lib\vpin-env.ps1")

$dir = Join-Path $ROOT "src\Pre_computed_table"
$script = Join-Path $dir "baby-step-giant-step.py"
$out = Join-Path $dir "table.pickle"

if (-not (Test-Path $script)) {
    Write-Host "[ERROR] 缺少 $script" -ForegroundColor Red
    exit 1
}

$py = Get-VpinPython -RepoRoot $ROOT
Write-Host "生成 BSGS table.pickle（约 30 分钟，请勿中断）..." -ForegroundColor Cyan
Write-Host "  Python: $py" -ForegroundColor Gray
Write-Host "  输出:   $out" -ForegroundColor Gray

Push-Location $dir
& $py baby-step-giant-step.py
Pop-Location

if (Test-Path $out) {
    $mb = [math]::Round((Get-Item $out).Length / 1MB, 1)
    Write-Host "`n[OK] 已生成 table.pickle (${mb} MB)" -ForegroundColor Green
    Write-Host "Rust 路线还需 table.bin（~208MB，不能进 GitHub）— 见 docs/环境配置与手动步骤.md §3.2" -ForegroundColor Yellow
} else {
    Write-Host "[ERROR] 未生成 table.pickle" -ForegroundColor Red
    exit 1
}
