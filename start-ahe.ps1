# MVP-AHE 一键部署启动脚本
# 用法: 在项目根目录右键「使用 PowerShell 运行」或执行 .\start-ahe.ps1
# 按 Ctrl+C 停止所有服务

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MVP-AHE 同态推理部署启动" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# ---------- 环境检查 ----------
$python = Join-Path $ROOT ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "[ERROR] 未找到 .venv, 请先执行: python -m venv .venv" -ForegroundColor Red
    exit 1
}

$bsgs = Join-Path $ROOT "src\Pre_computed_table\table.pickle"
if (-not (Test-Path $bsgs)) {
    Write-Host "[ERROR] 缺少 BSGS 预计算表: $bsgs" -ForegroundColor Red
    Write-Host "  首次部署须生成（约 30 分钟）:" -ForegroundColor Yellow
    Write-Host "    cd src\Pre_computed_table" -ForegroundColor Yellow
    Write-Host "    ..\..\..\.venv\Scripts\python.exe baby-step-giant-step.py" -ForegroundColor Yellow
    exit 1
}

# ---------- 检查模型权重 ----------
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
    Write-Host "[ERROR] 未找到模型权重。请确认 model_training/outputs/ 下有 npy 文件" -ForegroundColor Red
    Write-Host "  仓库已包含预训练权重，请检查 git clone 是否完整" -ForegroundColor Yellow
    exit 1
}
Write-Host "[CHECK] 模型权重: OK (model_training/outputs/)" -ForegroundColor Green

Write-Host "[CHECK] Python:  $( & $python --version 2>&1 )" -ForegroundColor Green
Write-Host "[CHECK] BSGS 表: $('{0:N0}' -f ((Get-Item $bsgs).Length / 1MB)) MB" -ForegroundColor Green

# ---------- 检查依赖 ----------
$missing = & $python -c "
import importlib, sys
pkgs = ['fastapi','uvicorn','ecdsa','numpy','websockets','PIL','torch','torchvision','pydantic','pydantic_settings']
miss = [p for p in pkgs if importlib.util.find_spec(p.split('.')[0] if '.' in p else p) is None]
if miss: print(','.join(miss))
" 2>&1
if ($missing -and $missing.ToString().Trim()) {
    Write-Host "[WARN] 缺少 Python 包: $missing" -ForegroundColor Yellow
    Write-Host "  自动安装中..." -ForegroundColor Yellow
    & (Join-Path $ROOT ".venv\Scripts\pip.exe") install -e (Join-Path $ROOT "vpin-client") | Out-Null
    & (Join-Path $ROOT ".venv\Scripts\pip.exe") install -r (Join-Path $ROOT "vpin-backend\requirements.txt") torch torchvision pillow websockets | Out-Null
}

# ---------- 检查端口 ----------
$port8000 = netstat -ano | Select-String "LISTENING" | Select-String ":8000 "
$port1420 = netstat -ano | Select-String "LISTENING" | Select-String ":1420 "
if ($port8000) {
    Write-Host "[WARN] 端口 8000 已被占用, 尝试释放..." -ForegroundColor Yellow
    $pid = ($port8000.ToString().Trim() -split '\s+')[-1]
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}
if ($port1420) {
    Write-Host "[WARN] 端口 1420 已被占用, 尝试释放..." -ForegroundColor Yellow
    $pid = ($port1420.ToString().Trim() -split '\s+')[-1]
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

# ---------- 启动后端 ----------
Write-Host "`n[1/2] 启动后端 (http://127.0.0.1:8000) ..." -ForegroundColor Cyan
$backend = Start-Process -FilePath $python `
    -ArgumentList "-m", "vpin_backend.main" `
    -WorkingDirectory (Join-Path $ROOT "vpin-backend") `
    -PassThru -WindowStyle Normal
Write-Host "  后端 PID: $($backend.Id)" -ForegroundColor Green
Start-Sleep -Seconds 3

# ---------- 检查 Node.js ----------
$frontendDir = Join-Path $ROOT "vpin_frontend\vpin-frontend"
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "[INFO] 首次运行, 安装前端依赖..." -ForegroundColor Yellow
    Push-Location $frontendDir
    npm install
    Pop-Location
}

# ---------- 检查 Rust ----------
$rustc = Get-Command rustc -ErrorAction SilentlyContinue
if (-not $rustc) {
    Write-Host "[ERROR] 未找到 Rust 工具链, 请安装: https://rustup.rs" -ForegroundColor Red
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    exit 1
}
Write-Host "[CHECK] Rust:    $(rustc --version)" -ForegroundColor Green

# ---------- 启动 Tauri ----------
Write-Host "[2/2] 启动 Tauri 桌面端 (首次编译约 1-3 分钟) ..." -ForegroundColor Cyan
$tauri = Start-Process -FilePath "npm" `
    -ArgumentList "run", "tauri", "dev" `
    -WorkingDirectory $frontendDir `
    -PassThru -WindowStyle Normal
Write-Host "  Tauri PID: $($tauri.Id)" -ForegroundColor Green

# ---------- 等待 ----------
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  部署完成！" -ForegroundColor Green
Write-Host "  后端 API:  http://127.0.0.1:8000" -ForegroundColor White
Write-Host "  Tauri 窗口: VDS-VPIN 工作台" -ForegroundColor White
Write-Host "  AHE 推理:  窗口内 → 模型仓库 → AHE 推理" -ForegroundColor White
Write-Host "  按 Enter 停止所有服务..." -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan

Read-Host | Out-Null

# ---------- 清理 ----------
Write-Host "`n正在停止服务..." -ForegroundColor Yellow
Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
Stop-Process -Id $tauri.Id -Force -ErrorAction SilentlyContinue
Get-Process -Name "vpin-frontend" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "已停止。" -ForegroundColor Green
