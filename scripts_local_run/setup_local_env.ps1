param(
    [string]$BasePython = "C:\Users\Frede\anaconda3\envs\BioTon\python.exe",
    [string]$Settings = "",
    [string]$EnvironmentRoot = "",
    [switch]$SkipBacpipe,
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"
$LocalRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $LocalRoot
if (-not $Settings) { $Settings = Join-Path $LocalRoot "local.settings.json" }
if (-not $EnvironmentRoot -and (Test-Path -LiteralPath $Settings)) {
    $LocalSettings = Get-Content -Raw -LiteralPath $Settings | ConvertFrom-Json
    $EnvironmentRoot = [string]$LocalSettings.environment_dir
}
if (-not $EnvironmentRoot) { $EnvironmentRoot = "D:\BioOTon_envs" }
$EnvironmentRoot = [Environment]::ExpandEnvironmentVariables($EnvironmentRoot)
if (-not [IO.Path]::IsPathRooted($EnvironmentRoot)) {
    $EnvironmentRoot = Join-Path $LocalRoot $EnvironmentRoot
}
$CoreEnv = Join-Path $EnvironmentRoot "core"
$BacpipeEnv = Join-Path $EnvironmentRoot "bacpipe"
$CorePython = Join-Path $CoreEnv "Scripts\python.exe"
$BacpipePython = Join-Path $BacpipeEnv "Scripts\python.exe"

if ($Recreate) {
    foreach ($Environment in @($CoreEnv, $BacpipeEnv)) {
        if (Test-Path -LiteralPath $Environment) {
            $Resolved = [IO.Path]::GetFullPath($Environment)
            if ($Resolved.Length -lt 8 -or $Resolved -eq [IO.Path]::GetPathRoot($Resolved)) {
                throw "Unsicherer Environment-Pfad fuer -Recreate: $Resolved"
            }
            Remove-Item -LiteralPath $Resolved -Recurse -Force
        }
    }
}

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

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Prefix) | Out-Null
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
