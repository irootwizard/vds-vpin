# First-time environment setup for MVP-AHE (Windows PowerShell).
# Usage (repo root):
#   .\scripts\setup.ps1
#   .\scripts\setup.ps1 -BuildRust -GenerateBsgsPickle

param(
    [switch]$BuildRust,
    [switch]$GenerateBsgsPickle,
    [switch]$SkipFrontend,
    [switch]$SkipTorch
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "lib\vpin-env.ps1")

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MVP-AHE 环境初始化 (setup.ps1)" -ForegroundColor Cyan
Write-Host "  Repo: $ROOT" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# --- Python ---
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyCmd) {
    Write-Host "[ERROR] 未找到 python，请安装 Python 3.10+ 并加入 PATH" -ForegroundColor Red
    exit 1
}
$ver = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([double]$ver -lt 3.10) {
    Write-Host "[ERROR] 需要 Python 3.10+，当前 $ver" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Python $(& python --version 2>&1)" -ForegroundColor Green

$venvPy = Join-Path $ROOT ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "[1/5] 创建虚拟环境 .venv ..." -ForegroundColor Cyan
    & python -m venv (Join-Path $ROOT ".venv")
} else {
    Write-Host "[1/5] 虚拟环境已存在" -ForegroundColor Green
}

$pip = Join-Path $ROOT ".venv\Scripts\pip.exe"
Write-Host "[2/5] 安装 Python 依赖 ..." -ForegroundColor Cyan
& $pip install -U pip wheel | Out-Null
& $pip install -e (Join-Path $ROOT "vpin-client") | Out-Null
& $pip install -r (Join-Path $ROOT "vpin-backend\requirements.txt") | Out-Null
if (-not $SkipTorch) {
    & $pip install torch torchvision pillow websockets | Out-Null
}
Write-Host "  vpin-client (editable) + vpin-backend + torch" -ForegroundColor Green

# --- Node ---
if (-not $SkipFrontend) {
    $frontend = Join-Path $ROOT "vpin_frontend\vpin-frontend"
    Write-Host "[3/5] 前端 npm install ..." -ForegroundColor Cyan
    Push-Location $frontend
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Host "[WARN] 未找到 npm，跳过前端依赖（Tauri 需要 Node 18+）" -ForegroundColor Yellow
    } else {
        npm install
        Write-Host "  npm install 完成" -ForegroundColor Green
    }
    Pop-Location
} else {
    Write-Host "[3/5] 跳过前端 (-SkipFrontend)" -ForegroundColor Yellow
}

# --- Rust stable (AHE + Tauri) ---
Write-Host "[4/5] 检查 Rust stable ..." -ForegroundColor Cyan
if (-not (Get-Command rustup -ErrorAction SilentlyContinue)) {
    Write-Host "[WARN] 未安装 rustup — Tauri / Rust AHE 需要: https://rustup.rs" -ForegroundColor Yellow
    Write-Host "       手动步骤见 docs/环境配置与手动步骤.md §1" -ForegroundColor Yellow
} else {
    rustup toolchain install stable 2>$null | Out-Null
    rustup default stable 2>$null | Out-Null
    Write-Host "  $(rustc --version)" -ForegroundColor Green
    if ($BuildRust) {
        & (Join-Path $PSScriptRoot "build-rust-ahe.ps1")
    }
}

# --- BSGS pickle (optional long run) ---
$pickle = Join-Path $ROOT "src\Pre_computed_table\table.pickle"
if ($GenerateBsgsPickle) {
    Write-Host "[5/5] 生成 table.pickle（约 30 分钟）..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "generate-bsgs-pickle.ps1")
} elseif (-not (Test-Path $pickle)) {
    Write-Host "[5/5] 缺少 BSGS table.pickle — Python 推理必需" -ForegroundColor Yellow
    Write-Host "  运行: .\scripts\generate-bsgs-pickle.ps1" -ForegroundColor Yellow
    Write-Host "  或见 docs/环境配置与手动步骤.md §3" -ForegroundColor Yellow
} else {
    $mb = [math]::Round((Get-Item $pickle).Length / 1MB, 1)
    Write-Host "[5/5] BSGS table.pickle 已存在 (${mb} MB)" -ForegroundColor Green
}

Write-Host "`n下一步:" -ForegroundColor Cyan
Write-Host "  .\scripts\check-env.ps1          # 预检" -ForegroundColor White
Write-Host "  .\start-ahe.ps1                # Python + Tauri" -ForegroundColor White
Write-Host "  .\scripts\build-rust-ahe.ps1   # 编译 ahe-cli / ahe-server" -ForegroundColor White
Write-Host "  手动步骤: docs/环境配置与手动步骤.md" -ForegroundColor White
