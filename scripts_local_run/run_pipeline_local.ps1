param(
    [ValidateSet("add_new_ids", "from_scratch", "functionality_test")]
    [string]$Mode = "add_new_ids",
    [string]$BasePython = "C:\Users\Frede\anaconda3\envs\BioTon\python.exe",
    [string]$Settings = "",
    [switch]$SkipEnvironmentSetup,
    [switch]$SkipMount,
    [switch]$SkipHorekaBootstrap,
    [switch]$RefreshHorekaOutputs,
    [switch]$SkipLsdfPublish,
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

$LocalSettings = Get-Content -Raw -LiteralPath $Settings | ConvertFrom-Json
$EnvironmentRoot = [string]$LocalSettings.environment_dir
if (-not $EnvironmentRoot) { $EnvironmentRoot = "D:\BioOTon_envs" }
$EnvironmentRoot = [Environment]::ExpandEnvironmentVariables($EnvironmentRoot)
if (-not [IO.Path]::IsPathRooted($EnvironmentRoot)) {
    $EnvironmentRoot = Join-Path $LocalRoot $EnvironmentRoot
}
$CorePython = Join-Path $EnvironmentRoot "core\Scripts\python.exe"
$BacpipePython = Join-Path $EnvironmentRoot "bacpipe\Scripts\python.exe"
if (-not $SkipEnvironmentSetup) {
    if ($Mode -eq "functionality_test") {
        & (Join-Path $LocalRoot "setup_local_env.ps1") `
            -BasePython $BasePython -Settings $Settings -SkipBacpipe
    }
    else {
        & (Join-Path $LocalRoot "setup_local_env.ps1") `
            -BasePython $BasePython -Settings $Settings
    }
    if ($LASTEXITCODE -ne 0) { throw "Lokales Environment-Setup fehlgeschlagen." }
}
if (-not (Test-Path -LiteralPath $CorePython)) { throw "Core Python fehlt: $CorePython" }
if (($Mode -ne "functionality_test") -and (-not (Test-Path -LiteralPath $BacpipePython))) {
    throw "Bacpipe Python fehlt: $BacpipePython"
}

if (($Mode -ne "functionality_test") -and (-not $SkipMount)) {
    & $CorePython (Join-Path $LocalRoot "mount_lsdf.py") --settings $Settings
    if ($LASTEXITCODE -ne 0) { throw "LSDF konnte nicht eingebunden werden." }
}

$BootstrapEnabled = if ($null -eq $LocalSettings.bootstrap_horeka_outputs) {
    $true
}
else {
    [bool]$LocalSettings.bootstrap_horeka_outputs
}
if (($Mode -eq "add_new_ids") -and (-not $SkipHorekaBootstrap) -and $BootstrapEnabled) {
    $BootstrapArguments = @((Join-Path $LocalRoot "sync_horeka_outputs.py"), "--settings", $Settings)
    if ($RefreshHorekaOutputs) { $BootstrapArguments += "--refresh" }
    & $CorePython @BootstrapArguments
    if ($LASTEXITCODE -ne 0) { throw "Horeka-Outputs konnten nicht lokal uebernommen werden." }
}

$Device = "cpu"
if (($Mode -ne "functionality_test") -and (-not $CpuOnly)) {
    $Detected = (& $BacpipePython -c "import torch; print('cuda' if torch.cuda.is_available() else 'cpu')" | Select-Object -Last 1)
    if ($Detected) { $Device = $Detected.Trim() }
}
if ($Mode -eq "functionality_test") { $BacpipePython = $CorePython }
Write-Host "Bioakustik-Geraet: $Device"

$GeneratedConfig = Join-Path $LocalRoot "config.local.generated.json"
$PrepareArgs = @(
    (Join-Path $LocalRoot "prepare_local_config.py"),
    "--settings", $Settings,
    "--source-config", (Join-Path $RepoRoot "config.horeka.json"),
    "--output-config", $GeneratedConfig,
    "--repo-root", $RepoRoot,
    "--device", $Device
)
if ($Mode -eq "functionality_test") { $PrepareArgs += "--skip-cache-copy" }
& $CorePython @PrepareArgs
if ($LASTEXITCODE -ne 0) { throw "Lokale Konfiguration konnte nicht erzeugt werden." }

& $CorePython (Join-Path $LocalRoot "local_orchestrator.py") `
    --mode $Mode `
    --config $GeneratedConfig `
    --repo-root $RepoRoot `
    --core-python $CorePython `
    --bacpipe-python $BacpipePython `
    --settings $Settings
$PipelineExitCode = $LASTEXITCODE

$PublishEnabled = if ($null -eq $LocalSettings.publish_successful_outputs_to_lsdf) {
    $true
}
else {
    [bool]$LocalSettings.publish_successful_outputs_to_lsdf
}
if (
    ($PipelineExitCode -eq 0) -and
    ($Mode -ne "functionality_test") -and
    (-not $SkipLsdfPublish) -and
    $PublishEnabled
) {
    & $CorePython (Join-Path $LocalRoot "publish_local_outputs.py") `
        --settings $Settings `
        --repo-root $RepoRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Lokaler Lauf war erfolgreich, aber die LSDF-Veroeffentlichung ist fehlgeschlagen."
    }
}
exit $PipelineExitCode
