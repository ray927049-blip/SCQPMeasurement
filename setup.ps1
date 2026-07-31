[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$ProjectPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ProjectUvCache = Join-Path $ProjectRoot ".uv-cache"
$ProjectRuntime = Join-Path $ProjectRoot ".runtime"

Push-Location $ProjectRoot
try {
    $UvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $UvCommand) {
        throw @"
uv is required for the one-command setup but was not found.
Install it once with:
  winget install --id Astral-sh.uv -e
Then run .\setup.cmd again.
"@
    }

    # Keep the package cache inside the project so restricted lab PCs work reliably.
    $env:UV_CACHE_DIR = $ProjectUvCache
    $env:TEMP = Join-Path $ProjectRuntime "temp"
    $env:TMP = $env:TEMP
    $env:MPLCONFIGDIR = Join-Path $ProjectRuntime "matplotlib"
    New-Item -ItemType Directory -Force -Path $env:TEMP, $env:MPLCONFIGDIR | Out-Null

    Write-Host "[1/4] Ensuring a uv-managed Python 3.12 is installed..."
    & uv python install 3.12
    if ($LASTEXITCODE -ne 0) { throw "uv could not install/find Python 3.12." }

    Write-Host "[2/4] Creating/updating .venv and installing project + dev dependencies..."
    & uv sync --python 3.12 --extra dev
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed." }

    $LocalConfig = Join-Path $ProjectRoot "hardware_config.json"
    $ExampleConfig = Join-Path $ProjectRoot "hardware_config.example.json"
    if (-not (Test-Path -LiteralPath $LocalConfig)) {
        Copy-Item -LiteralPath $ExampleConfig -Destination $LocalConfig
        Write-Host "Created local hardware_config.json from the example."
    }

    if (-not (Test-Path -LiteralPath $ProjectPython)) {
        throw "Setup completed without creating $ProjectPython"
    }

    Write-Host "[3/4] Verifying the selected Python..."
    & $ProjectPython -c "import sys; assert sys.version_info[:2] == (3, 12), sys.version; print(sys.version)"
    if ($LASTEXITCODE -ne 0) { throw "The project environment is not using Python 3.12." }

    Write-Host "[4/4] Running the test suite..."
    $PytestTemp = Join-Path $ProjectRuntime "pytest-temp"
    $PytestCache = Join-Path $ProjectRuntime "pytest-cache"
    & $ProjectPython -m pytest -q --basetemp $PytestTemp -o "cache_dir=$PytestCache"
    if ($LASTEXITCODE -ne 0) { throw "Tests failed after installation." }

    Write-Host ""
    Write-Host "Setup succeeded."
    Write-Host "Activate in PowerShell with:"
    Write-Host "  Set-ExecutionPolicy -Scope Process Bypass -Force"
    Write-Host "  .\.venv\Scripts\Activate.ps1"
    Write-Host "Or run without activation:"
    Write-Host "  .\.venv\Scripts\python.exe -m experiments.dummy_measurement --config hardware_config.json"
}
finally {
    Pop-Location
}
