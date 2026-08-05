param(
    [string]$Settings = "",
    [ValidateSet("size", "sha256")]
    [string]$Verification = "size",
    [switch]$DryRun,
    [switch]$SkipMount,
    [switch]$KeepCompletedParquetChunks
)

$ErrorActionPreference = "Stop"
$LocalRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Settings) { $Settings = Join-Path $LocalRoot "local.settings.json" }
if (-not (Test-Path -LiteralPath $Settings)) {
    throw "Lokale Settings fehlen: $Settings"
}
$LocalSettings = Get-Content -Raw -LiteralPath $Settings | ConvertFrom-Json
$EnvironmentRoot = [Environment]::ExpandEnvironmentVariables([string]$LocalSettings.environment_dir)
if (-not $EnvironmentRoot) { $EnvironmentRoot = "D:\BioOTon_envs" }
$Python = Join-Path $EnvironmentRoot "core\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { throw "Core Python fehlt: $Python" }

if (-not $SkipMount) {
    & $Python (Join-Path $LocalRoot "mount_lsdf.py") --settings $Settings
    if ($LASTEXITCODE -ne 0) { throw "LSDF konnte nicht eingebunden werden." }
}

$Arguments = @(
    (Join-Path $LocalRoot "offload_step2_local_storage.py"),
    "--settings", $Settings,
    "--verification", $Verification
)
if ($DryRun) { $Arguments += "--dry-run" }
if ($KeepCompletedParquetChunks) { $Arguments += "--no-completed-parquet" }

& $Python @Arguments
if ($LASTEXITCODE -ne 0) { throw "Step-2-Auslagerung fehlgeschlagen." }
