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
    if ($env:VPIN_PLATFORM_ROOT -and (Test-Path $env:VPIN_PLATFORM_ROOT)) {
        return (Resolve-Path $env:VPIN_PLATFORM_ROOT).Path
    }
    return (Join-Path $RepoRoot "vpin-client")
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

function Get-AheCliBin {
    param([string]$ClientRoot = (Get-VpinClientRoot))
    foreach ($profile in @("release", "debug")) {
        $win = Join-Path $ClientRoot "target\$profile\ahe-cli.exe"
        if (Test-Path $win) { return (Resolve-Path $win).Path }
        $unix = Join-Path $ClientRoot "target\$profile\ahe-cli"
        if (Test-Path $unix) { return (Resolve-Path $unix).Path }
    }
    return (Join-Path $ClientRoot "target\release\ahe-cli.exe")
}

function Get-AheServerBin {
    param([string]$BackendRoot = (Get-VpinBackendRoot))
    foreach ($profile in @("release", "debug")) {
        $win = Join-Path $BackendRoot "target\$profile\ahe-server.exe"
        if (Test-Path $win) { return (Resolve-Path $win).Path }
        $unix = Join-Path $BackendRoot "target\$profile\ahe-server"
        if (Test-Path $unix) { return (Resolve-Path $unix).Path }
    }
    return (Join-Path $BackendRoot "target\release\ahe-server.exe")
}

function Set-VpinDefaultEnv {
    param([string]$RepoRoot = (Get-VpinRepoRoot))
    $env:VPIN_REPO_ROOT = $RepoRoot
    if (-not $env:VPIN_CLIENT_ROOT) { $env:VPIN_CLIENT_ROOT = Join-Path $RepoRoot "vpin-client" }
    if (-not $env:VPIN_BACKEND_ROOT) { $env:VPIN_BACKEND_ROOT = Join-Path $RepoRoot "vpin-backend" }
}

function Test-VpinPortListening {
    param([int]$Port)
    return [bool](netstat -ano | Select-String "LISTENING" | Select-String ":$Port ")
}

function Stop-VpinPort {
    param([int]$Port)
    $line = netstat -ano | Select-String "LISTENING" | Select-String ":$Port " | Select-Object -First 1
    if ($line) {
        $pid = ($line.ToString().Trim() -split '\s+')[-1]
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
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
