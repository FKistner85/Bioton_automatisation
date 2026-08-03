Exit code: 0
Wall time: 3 seconds
Output:
param(
    [string]$BasePython = "C:\Users\Frede\anaconda3\envs\BioTon\python.exe",
    [switch]$SkipBacpipe
)

$ErrorActionPreference = "Stop"
$LocalRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $LocalRoot
$CoreEnv = Join-Path $LocalRoot ".venv_local"
$BacpipeEnv = Join-Path $LocalRoot ".venv_local_bacpipe"
$CorePython = Join-Path $CoreEnv "Scripts\python.exe"
$BacpipePython = Join-Path $BacpipeEnv "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $BasePython)) {
    $PyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $PyLauncher) {
        throw "Python 3.11 wurde nicht gefunden. Erwartet: $BasePython"
    }
    $BasePythonArgs = @("-3.11")
    $BasePythonCommand = $PyLauncher.Source
}
else {
    $BasePythonArgs = @()
    $BasePythonCommand = $BasePython
}

function New-OrUpdateEnvironment {
    param(
        [string]$Prefix,
        [string]$Python,
        [string[]]$Requirements
    )

    if (-not (Test-Path -LiteralPath $Python)) {
        & $BasePythonCommand @BasePythonArgs -m venv $Prefix
        if ($LASTEXITCODE -ne 0) { throw "Virtuelle Umgebung konnte nicht erstellt werden: $Prefix" }
    }
    & $Python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip-Upgrade fehlgeschlagen: $Prefix" }
    foreach ($Requirement in $Requirements) {
        & $Python -m pip install -r $Requirement
        if ($LASTEXITCODE -ne 0) { throw "Dependency-Installation fehlgeschlagen: $Requirement" }
    }
}

New-OrUpdateEnvironment `
    -Prefix $CoreEnv `
    -Python $CorePython `
    -Requirements @((Join-Path $LocalRoot "requirements.local.txt"))

& $CorePython -c "import pandas, geopandas, pyogrio, shapely, pyarrow, av, rasterio, xarray, rioxarray, keyring, paramiko, psutil; print('Core environment OK')"
if ($LASTEXITCODE -ne 0) { throw "Core dependency preflight fehlgeschlagen." }

if (-not $SkipBacpipe) {
    New-OrUpdateEnvironment `
        -Prefix $BacpipeEnv `
        -Python $BacpipePython `
        -Requirements @(
            (Join-Path $RepoRoot "requirements.bacpipe.txt")
        )
    & $BacpipePython -c "import bacpipe, pandas, pyarrow, torch; print('Bacpipe environment OK; CUDA:', torch.cuda.is_available())"
    if ($LASTEXITCODE -ne 0) { throw "Bacpipe dependency preflight fehlgeschlagen." }
}

Write-Host "Core Python:    $CorePython"
if (-not $SkipBacpipe) { Write-Host "Bacpipe Python: $BacpipePython" }

