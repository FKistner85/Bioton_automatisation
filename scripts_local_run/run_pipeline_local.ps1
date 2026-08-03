param(
    [ValidateSet("add_new_ids", "from_scratch", "functionality_test")]
    [string]$Mode = "add_new_ids",
    [string]$BasePython = "C:\Users\Frede\anaconda3\envs\BioTon\python.exe",
    [string]$Settings = "",
    [switch]$SkipEnvironmentSetup,
    [switch]$SkipMount,
    [switch]$CpuOnly
)

$ErrorActionPreference = "Stop"
$LocalRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $LocalRoot
Set-Location $RepoRoot

if (-not $Settings) { $Settings = Join-Path $LocalRoot "local.settings.json" }
$ExampleSettings = Join-Path $LocalRoot "local.settings.example.json"
if (-not (Test-Path -LiteralPath $Settings)) {
    Copy-Item -LiteralPath $ExampleSettings -Destination $Settings
    Write-Host "Lokale Einstellungen erzeugt: $Settings"
}

$CorePython = Join-Path $LocalRoot ".venv_local\Scripts\python.exe"
$BacpipePython = Join-Path $LocalRoot ".venv_local_bacpipe\Scripts\python.exe"
if (-not $SkipEnvironmentSetup) {
    & (Join-Path $LocalRoot "setup_local_env.ps1") -BasePython $BasePython
    if ($LASTEXITCODE -ne 0) { throw "Lokales Environment-Setup fehlgeschlagen." }
}
if (-not (Test-Path -LiteralPath $CorePython)) { throw "Core Python fehlt: $CorePython" }
if (-not (Test-Path -LiteralPath $BacpipePython)) { throw "Bacpipe Python fehlt: $BacpipePython" }

if (-not $SkipMount) {
    & $CorePython (Join-Path $LocalRoot "mount_lsdf.py") --settings $Settings
    if ($LASTEXITCODE -ne 0) { throw "LSDF konnte nicht eingebunden werden." }
}

$Device = "cpu"
if (-not $CpuOnly) {
    $Detected = (& $BacpipePython -c "import torch; print('cuda' if torch.cuda.is_available() else 'cpu')" | Select-Object -Last 1)
    if ($Detected) { $Device = $Detected.Trim() }
}
Write-Host "Bioakustik-Geraet: $Device"

$GeneratedConfig = Join-Path $LocalRoot "config.local.generated.json"
& $CorePython (Join-Path $LocalRoot "prepare_local_config.py") `
    --settings $Settings `
    --source-config (Join-Path $RepoRoot "config.horeka.json") `
    --output-config $GeneratedConfig `
    --repo-root $RepoRoot `
    --device $Device
if ($LASTEXITCODE -ne 0) { throw "Lokale Konfiguration konnte nicht erzeugt werden." }

& $CorePython (Join-Path $LocalRoot "local_orchestrator.py") `
    --mode $Mode `
    --config $GeneratedConfig `
    --repo-root $RepoRoot `
    --core-python $CorePython `
    --bacpipe-python $BacpipePython `
    --settings $Settings
exit $LASTEXITCODE

