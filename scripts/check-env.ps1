# Pre-flight checks before MVP-AHE run.
# Usage: .\scripts\check-env.ps1 [-Strict] [-RequireRust] [-RequireBsgsBin]

param(
    [switch]$Strict,
    [switch]$RequireRust,
    [switch]$RequireBsgsBin
)

$ErrorActionPreference = "Continue"
$ROOT = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "lib\vpin-env.ps1")

$fail = 0
$warn = 0

function Pass([string]$msg) { Write-Host "[OK]   $msg" -ForegroundColor Green }
function Fail([string]$msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red; $script:fail++ }
function Warn([string]$msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow; $script:warn++ }

Write-Host "MVP-AHE env check: $ROOT" -ForegroundColor Cyan
Write-Host ""

$py = Join-Path $ROOT ".venv\Scripts\python.exe"
if (Test-Path $py) {
    Pass "Python venv"
} else {
    Fail "Missing .venv - run scripts\setup.ps1"
}

if (Test-Path $py) {
    $pyCheck = Join-Path $env:TEMP "vpin_pkg_check.py"
    @'
import importlib.util
pkgs = ["fastapi","uvicorn","ecdsa","numpy","websockets","PIL","torch","torchvision","pydantic","pydantic_settings","gmpy2"]
miss = [p for p in pkgs if importlib.util.find_spec(p.split(".")[0]) is None]
print(",".join(miss))
'@ | Set-Content -Path $pyCheck -Encoding UTF8
    $missing = & $py $pyCheck 2>&1
    Remove-Item $pyCheck -Force -ErrorAction SilentlyContinue
    if ($missing -and $missing.ToString().Trim()) {
        Fail "Missing Python packages: $missing"
    } else {
        Pass "Python packages"
    }
}

$pickle = Get-VpinBsgsPickle -RepoRoot $ROOT
if (Test-Path $pickle) {
    $mb = [math]::Round((Get-Item $pickle).Length / 1MB, 1)
    Pass "BSGS table.pickle (${mb} MB)"
} else {
    Fail "Missing table.pickle - run scripts\generate-bsgs-pickle.ps1"
}

$bin = Get-VpinBsgsBin -RepoRoot $ROOT
if (Test-Path $bin) {
    $mb = [math]::Round((Get-Item $bin).Length / 1MB, 1)
    Pass "BSGS table.bin (${mb} MB)"
} elseif ($RequireBsgsBin) {
    Fail "Missing table.bin - see docs/环境配置与手动步骤.md"
} else {
    Warn "Missing table.bin - Rust engines disabled"
}

$hasW = $false
foreach ($r in @("model_training\outputs\20260622_184254", "model_training\outputs\20260623_185935")) {
    $p = Join-Path $ROOT $r
    if ((Test-Path $p) -and (Get-ChildItem $p -Filter "*.npy" -ErrorAction SilentlyContinue).Count -gt 0) {
        $hasW = $true
        break
    }
}
if ($hasW) { Pass "model_training/outputs weights" } else { Fail "Missing npy weights" }

$reg = Join-Path $ROOT "vpin-backend\data\models\registry.json"
if (Test-Path $reg) { Pass "registry.json" } else { Fail "Missing registry.json" }

$nm = Join-Path $ROOT "vpin_frontend\vpin-frontend\node_modules"
if (Test-Path $nm) { Pass "node_modules" } else { Warn "Missing node_modules - run scripts\setup.ps1" }

if (Get-Command rustc -ErrorAction SilentlyContinue) {
    Pass "Rust $(rustc --version)"
} elseif ($RequireRust) {
    Fail "Rust not installed"
} else {
    Warn "Rust not installed"
}

$cli = Get-AheCliBin -ClientRoot (Get-VpinClientRoot -RepoRoot $ROOT)
if (Test-Path $cli) {
    Pass "ahe-cli"
} elseif ($RequireRust) {
    Fail "ahe-cli not built - scripts\build-rust-ahe.ps1"
} else {
    Warn "ahe-cli not built"
}

$srv = Get-AheServerBin -BackendRoot (Get-VpinBackendRoot -RepoRoot $ROOT)
if (Test-Path $srv) {
    Pass "ahe-server"
} elseif ($RequireRust) {
    Fail "ahe-server not built - scripts\build-rust-ahe.ps1"
} else {
    Warn "ahe-server not built"
}

foreach ($port in @(8000, 8001, 8002, 1420)) {
    if (Test-VpinPortListening -Port $port) {
        Warn "Port $port in use"
    }
}

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path $vswhere) {
    $cpp = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null
    if ($cpp) { Pass "VS C++ Build Tools" } else { Warn "VS C++ workload not detected" }
} else {
    Warn "vswhere not found - install VS Build Tools if Tauri fails"
}

Write-Host ""
Write-Host "Summary: FAIL=$fail WARN=$warn" -ForegroundColor $(if ($fail -gt 0) { "Red" } elseif ($warn -gt 0) { "Yellow" } else { "Green" })
if ($Strict -and $warn -gt 0) { exit 2 }
if ($fail -gt 0) { exit 1 }
exit 0
