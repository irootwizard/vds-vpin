# Build image and run OVDS Docker tests.
param(
    [switch]$Protocol
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Image = if ($env:OVDS_IMAGE) { $env:OVDS_IMAGE } else { "vpin/ovds-reference:latest" }

Push-Location $Root
try {
    Write-Host "==> docker build -t $Image ."
    docker build -t $Image .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "==> docker run --rm $Image  (charm smoke test)"
    docker run --rm $Image
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    if ($Protocol) {
        Write-Host "==> docker run --rm $Image python src/test/test_all.py"
        docker run --rm $Image python src/test/test_all.py
    }

    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
