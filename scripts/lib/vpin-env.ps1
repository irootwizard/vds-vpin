# Shared path helpers for MVP-AHE scripts (dot-source from repo root scripts).

function Get-VpinRepoRoot {
    if ($env:VPIN_REPO_ROOT -and (Test-Path $env:VPIN_REPO_ROOT)) {
        return (Resolve-Path $env:VPIN_REPO_ROOT).Path
    }
    $here = $PSScriptRoot
    while ($here) {
        if ((Test-Path (Join-Path $here "vpin-client")) -and (Test-Path (Join-Path $here "vpin-backend"))) {
            return (Resolve-Path $here).Path
        }
        $parent = Split-Path $here -Parent
        if ($parent -eq $here) { break }
        $here = $parent
    }
    throw "Cannot locate vPIN-main repo root (set VPIN_REPO_ROOT)"
}

function Get-VpinClientRoot {
    param([string]$RepoRoot = (Get-VpinRepoRoot))
    if ($env:VPIN_CLIENT_ROOT -and (Test-Path $env:VPIN_CLIENT_ROOT)) {
        return (Resolve-Path $env:VPIN_CLIENT_ROOT).Path
    }
    return (Join-Path $RepoRoot "vpin-client")
}

function Get-VpinPlatformRoot {
    param([string]$RepoRoot = (Get-VpinRepoRoot))
    if ($env:VPIN_PLATFORM_ROOT -and (Test-Path $env:VPIN_PLATFORM_ROOT)) {
        return (Resolve-Path $env:VPIN_PLATFORM_ROOT).Path
    }
    $sibling = Join-Path (Split-Path $RepoRoot -Parent) "vpin-platform"
    if (Test-Path (Join-Path $sibling "Cargo.toml")) {
        return (Resolve-Path $sibling).Path
    }
    return $null
}

function Get-VpinConsoleDir {
    param([string]$RepoRoot = (Get-VpinRepoRoot))
    return (Join-Path $RepoRoot "vpin-console")
}

function Get-VpinLegacyFrontendDir {
    param([string]$RepoRoot = (Get-VpinRepoRoot))
    return (Join-Path $RepoRoot "vpin_frontend\vpin-frontend")
}

function Get-VpinFrontendDir {
    param([string]$RepoRoot = (Get-VpinRepoRoot))
    if ($env:VPIN_UI -eq "legacy") {
        return (Get-VpinLegacyFrontendDir -RepoRoot $RepoRoot)
    }
    return (Get-VpinConsoleDir -RepoRoot $RepoRoot)
}

function Get-VpinBackendRoot {
    param([string]$RepoRoot = (Get-VpinRepoRoot))
    if ($env:VPIN_BACKEND_ROOT -and (Test-Path $env:VPIN_BACKEND_ROOT)) {
        return (Resolve-Path $env:VPIN_BACKEND_ROOT).Path
    }
    return (Join-Path $RepoRoot "vpin-backend")
}

function Get-VpinPython {
    param([string]$RepoRoot = (Get-VpinRepoRoot))
    $py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) {
        throw "Missing $py — run scripts\setup.ps1"
    }
    return $py
}

function Get-VpinPip {
    param([string]$RepoRoot = (Get-VpinRepoRoot))
    return (Join-Path $RepoRoot ".venv\Scripts\pip.exe")
}

function Get-VpinBsgsPickle {
    param([string]$RepoRoot = (Get-VpinRepoRoot))
    if ($env:VPIN_BSGS_TABLE -and $env:VPIN_BSGS_TABLE -match '\.pickle$' -and (Test-Path $env:VPIN_BSGS_TABLE)) {
        return (Resolve-Path $env:VPIN_BSGS_TABLE).Path
    }
    return (Join-Path $RepoRoot "src\Pre_computed_table\table.pickle")
}

function Get-VpinBsgsBin {
    param(
        [string]$RepoRoot = (Get-VpinRepoRoot),
        [string]$ClientRoot = (Get-VpinClientRoot)
    )
    if ($env:VPIN_BSGS_TABLE -and $env:VPIN_BSGS_TABLE -match '\.bin$' -and (Test-Path $env:VPIN_BSGS_TABLE)) {
        return (Resolve-Path $env:VPIN_BSGS_TABLE).Path
    }
    $fixture = Join-Path $ClientRoot "tests\fixtures\table.bin"
    if (Test-Path $fixture) { return (Resolve-Path $fixture).Path }
    $fallback = Join-Path $RepoRoot "src\Pre_computed_table\table.bin"
    if (Test-Path $fallback) { return (Resolve-Path $fallback).Path }
    # sibling vpin-platform (legacy layout)
    $sibling = Join-Path (Split-Path $RepoRoot -Parent) "vpin-platform\tests\fixtures\table.bin"
    if (Test-Path $sibling) { return (Resolve-Path $sibling).Path }
    return $fixture
}

function Find-RustBinary {
    param(
        [string[]]$SearchRoots,
        [string]$Name
    )
    foreach ($root in ($SearchRoots | Where-Object { $_ -and (Test-Path $_) })) {
        foreach ($profile in @("release", "debug")) {
            $win = Join-Path $root "target\$profile\$Name.exe"
            if (Test-Path $win) { return (Resolve-Path $win).Path }
            $unix = Join-Path $root "target\$profile\$Name"
            if (Test-Path $unix) { return (Resolve-Path $unix).Path }
        }
    }
    return $null
}

function Get-AheCliBin {
    param([string]$RepoRoot = (Get-VpinRepoRoot))
    $found = Find-RustBinary -SearchRoots @(
        (Get-VpinClientRoot -RepoRoot $RepoRoot),
        (Get-VpinPlatformRoot -RepoRoot $RepoRoot)
    ) -Name "ahe-cli"
    if ($found) { return $found }
    return (Join-Path (Get-VpinClientRoot -RepoRoot $RepoRoot) "target\release\ahe-cli.exe")
}

function Get-AheServerBin {
    param([string]$RepoRoot = (Get-VpinRepoRoot))
    $found = Find-RustBinary -SearchRoots @(
        (Get-VpinBackendRoot -RepoRoot $RepoRoot),
        (Get-VpinPlatformRoot -RepoRoot $RepoRoot)
    ) -Name "ahe-server"
    if ($found) { return $found }
    return (Join-Path (Get-VpinBackendRoot -RepoRoot $RepoRoot) "target\release\ahe-server.exe")
}

function Get-AheServerWorkdir {
    param(
        [string]$RepoRoot = (Get-VpinRepoRoot),
        [string]$ServerBin = (Get-AheServerBin -RepoRoot $RepoRoot)
    )
    $norm = $ServerBin -replace '\\', '/'
    if ($norm -match '/vpin-backend/') {
        return (Get-VpinBackendRoot -RepoRoot $RepoRoot)
    }
    $platform = Get-VpinPlatformRoot -RepoRoot $RepoRoot
    if ($platform -and $norm -match '/vpin-platform/') {
        return $platform
    }
    return (Split-Path (Split-Path $ServerBin -Parent) -Parent)
}

function Test-VpinModelWeights {
    param([string]$RepoRoot = (Get-VpinRepoRoot))
    $outputs = Join-Path $RepoRoot "model_training\outputs"
    if (-not (Test-Path $outputs)) { return $false }
    foreach ($run in Get-ChildItem $outputs -Directory -ErrorAction SilentlyContinue) {
        if ((Get-ChildItem $run.FullName -Filter "*.npy" -ErrorAction SilentlyContinue).Count -gt 0) {
            return $true
        }
    }
    return $false
}

function Set-VpinDefaultEnv {
    param([string]$RepoRoot = (Get-VpinRepoRoot))
    $env:VPIN_REPO_ROOT = $RepoRoot
    if (-not $env:VPIN_CLIENT_ROOT) { $env:VPIN_CLIENT_ROOT = Join-Path $RepoRoot "vpin-client" }
    if (-not $env:VPIN_BACKEND_ROOT) { $env:VPIN_BACKEND_ROOT = Join-Path $RepoRoot "vpin-backend" }
    $platform = Get-VpinPlatformRoot -RepoRoot $RepoRoot
    if ($platform -and -not $env:VPIN_PLATFORM_ROOT) { $env:VPIN_PLATFORM_ROOT = $platform }
}

function New-VpinProcessCommand {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList = @(),
        [string]$WorkingDirectory,
        [hashtable]$Environment = @{}
    )
    $parts = @()
    foreach ($key in ($Environment.Keys | Sort-Object)) {
        $v = [string]$Environment[$key] -replace "'", "''"
        $parts += "`$env:$key='$v';"
    }
    if ($WorkingDirectory) {
        $wd = (Resolve-Path $WorkingDirectory).Path -replace "'", "''"
        $parts += "Set-Location -LiteralPath '$wd';"
    }
    if (Test-Path -LiteralPath $FilePath) {
        $exe = (Resolve-Path -LiteralPath $FilePath).Path -replace "'", "''"
        $invoke = "& '$exe'"
    } else {
        $name = $FilePath -replace "'", "''"
        $invoke = "& '$name'"
    }
    if ($ArgumentList -and $ArgumentList.Count -gt 0) {
        $argStr = ($ArgumentList | ForEach-Object {
            if ($_ -match '\s') { "'$($_ -replace "'", "''")'" } else { $_ }
        }) -join ' '
        $parts += "$invoke $argStr"
    } else {
        $parts += $invoke
    }
    return ($parts -join ' ')
}

function Start-VpinDetachedProcess {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [string]$WorkingDirectory,
        [hashtable]$Environment = @{},
        [ValidateSet("Normal", "Hidden", "Minimized")]
        [string]$WindowStyle = "Normal"
    )
    $cmd = New-VpinProcessCommand -FilePath $FilePath -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory -Environment $Environment
    return Start-Process powershell -ArgumentList @("-NoExit", "-Command", $cmd) `
        -PassThru -WindowStyle $WindowStyle
}

function Start-VpinPythonBackend {
    param(
        [string]$RepoRoot = (Get-VpinRepoRoot),
        [int]$Port = 8000,
        [switch]$Detach
    )
    Set-VpinDefaultEnv -RepoRoot $RepoRoot
    $python = Get-VpinPython -RepoRoot $RepoRoot
    $backend = Get-VpinBackendRoot -RepoRoot $RepoRoot
    $envBlock = @{
        VPIN_REPO_ROOT = $RepoRoot
    }
    if ($Detach) {
        Stop-VpinPort -Port $Port
        return Start-VpinDetachedProcess -FilePath $python `
            -ArgumentList @("-m", "vpin_backend.main") `
            -WorkingDirectory $backend -Environment $envBlock
    }
    return Start-Process -FilePath $python `
        -ArgumentList @("-m", "vpin_backend.main") `
        -WorkingDirectory $backend -PassThru -WindowStyle Normal
}

function Start-VpinRustServer {
    param(
        [string]$RepoRoot = (Get-VpinRepoRoot),
        [Parameter(Mandatory)][int]$Port,
        [switch]$Detach
    )
    Set-VpinDefaultEnv -RepoRoot $RepoRoot
    $server = Get-AheServerBin -RepoRoot $RepoRoot
    $workdir = Get-AheServerWorkdir -RepoRoot $RepoRoot -ServerBin $server
    $bsgs = Get-VpinBsgsBin -RepoRoot $RepoRoot
    if (-not (Test-Path $server)) { throw "ahe-server not found — run scripts\build-rust-ahe.ps1" }
    if (-not (Test-Path $bsgs)) { throw "table.bin not found — see docs/环境配置与手动步骤.md §3.2" }
    $envBlock = @{
        VPIN_REPO_ROOT   = $RepoRoot
        VPIN_BSGS_TABLE  = $bsgs
        AHE_SERVER_HOST  = "127.0.0.1"
        AHE_SERVER_PORT  = "$Port"
    }
    Stop-VpinPort -Port $Port
    if ($Detach) {
        return Start-VpinDetachedProcess -FilePath $server `
            -WorkingDirectory $workdir -Environment $envBlock
    }
    $env:VPIN_REPO_ROOT = $RepoRoot
    $env:VPIN_BSGS_TABLE = $bsgs
    $env:AHE_SERVER_HOST = "127.0.0.1"
    $env:AHE_SERVER_PORT = "$Port"
    return Start-Process -FilePath $server -WorkingDirectory $workdir -PassThru -WindowStyle Normal
}

function Test-VpinPortListening {
    param([int]$Port)
    return [bool](netstat -ano | Select-String "LISTENING" | Select-String ":$Port ")
}

function Stop-VpinPort {
    param([int]$Port)
    $line = netstat -ano | Select-String "LISTENING" | Select-String ":$Port " | Select-Object -First 1
    if ($line) {
        $processId = ($line.ToString().Trim() -split '\s+')[-1]
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
}

function Wait-VpinHttpHealth {
    param([int]$Port, [int]$TimeoutSec = 60)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/v1/health" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) { return $true }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    return $false
}
