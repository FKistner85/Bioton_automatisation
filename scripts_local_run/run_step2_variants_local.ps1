param(
    [ValidateSet("add_new_ids", "from_scratch")]
    [string]$Mode = "add_new_ids",
    [string]$BasePython = "C:\Users\Frede\anaconda3\envs\BioTon\python.exe",
    [string]$Settings = "",
    [switch]$SkipEnvironmentSetup,
    [switch]$SkipMount,
    [switch]$SkipLsdfPublish
)

$ErrorActionPreference = "Stop"
$LocalRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $LocalRoot
Set-Location $RepoRoot
if (-not $Settings) { $Settings = Join-Path $LocalRoot "local.settings.json" }
if (-not (Test-Path -LiteralPath $Settings)) {
    Copy-Item -LiteralPath (Join-Path $LocalRoot "local.settings.example.json") -Destination $Settings
}
$LocalSettings = Get-Content -Raw -LiteralPath $Settings | ConvertFrom-Json
$EnvironmentRoot = [Environment]::ExpandEnvironmentVariables([string]$LocalSettings.environment_dir)
if (-not $EnvironmentRoot) { $EnvironmentRoot = "D:\BioOTon_envs" }
$CorePython = Join-Path $EnvironmentRoot "core\Scripts\python.exe"
if (-not $SkipEnvironmentSetup) {
    & (Join-Path $LocalRoot "setup_local_env.ps1") -BasePython $BasePython -Settings $Settings -SkipBacpipe
    if ($LASTEXITCODE -ne 0) { throw "Lokales Environment-Setup fehlgeschlagen." }
}
if (-not (Test-Path -LiteralPath $CorePython)) { throw "Core Python fehlt: $CorePython" }
if (-not $SkipMount) {
    & $CorePython (Join-Path $LocalRoot "mount_lsdf.py") --settings $Settings
    if ($LASTEXITCODE -ne 0) { throw "LSDF konnte nicht eingebunden werden." }
}

$GeneratedConfig = Join-Path $LocalRoot "config.local.generated.json"
& $CorePython (Join-Path $LocalRoot "prepare_local_config.py") `
    --settings $Settings `
    --source-config (Join-Path $RepoRoot "config.horeka.json") `
    --output-config $GeneratedConfig `
    --repo-root $RepoRoot `
    --device cpu
if ($LASTEXITCODE -ne 0) { throw "Lokale Konfiguration konnte nicht erzeugt werden." }

$GeneratedSettings = Get-Content -Raw -LiteralPath $GeneratedConfig | ConvertFrom-Json
$SettingsWorkers = [int]$LocalSettings.max_parallel_steps
$ConfigWorkers = [int]$GeneratedSettings.lrt_variants.local_max_parallel_variants
if ($SettingsWorkers -lt 1) { $SettingsWorkers = 1 }
if ($ConfigWorkers -lt 1) { $ConfigWorkers = 1 }
$VariantWorkers = [Math]::Min($SettingsWorkers, $ConfigWorkers)
$RunId = "local_step2_variants_$(Get-Date -Format 'yyyyMMddTHHmmss')_$PID"
$LockTool = Join-Path $RepoRoot "tools\pipeline_lock.py"

& $CorePython $LockTool --config $GeneratedConfig acquire --run-id $RunId --owner-pid $PID
if ($LASTEXITCODE -ne 0) { throw "Pipeline-Lock konnte nicht gesetzt werden." }
$LockAcquired = $true
try {
    $Arguments = @(
        (Join-Path $RepoRoot "tools\step2_variants.py"),
        "--config", $GeneratedConfig,
        "--python", $CorePython,
        "--all-stages",
        "--max-workers", [string]$VariantWorkers
    )
    if ($Mode -eq "from_scratch") { $Arguments += "--force" }
    & $CorePython @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Lokaler Step-2-Variantenlauf fehlgeschlagen." }

    & $CorePython (Join-Path $RepoRoot "scripts\Step_7_1_update_formation_variant_table.py") `
        --config $GeneratedConfig
    if ($LASTEXITCODE -ne 0) { throw "Varianten-Mastertable fehlgeschlagen." }
    & $CorePython (Join-Path $RepoRoot "scripts\Step_7_0_update_master_table.py") `
        --config $GeneratedConfig
    if ($LASTEXITCODE -ne 0) { throw "Mastertable-Update fehlgeschlagen." }

    if (-not $SkipLsdfPublish) {
        & $CorePython (Join-Path $LocalRoot "publish_local_outputs.py") `
            --settings $Settings --repo-root $RepoRoot
        if ($LASTEXITCODE -ne 0) { throw "LSDF-Veroeffentlichung fehlgeschlagen." }
    }
}
finally {
    if ($LockAcquired) {
        & $CorePython $LockTool --config $GeneratedConfig release --run-id $RunId
    }
}
