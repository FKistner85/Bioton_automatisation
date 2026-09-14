param(
    [string]$BasePython = "C:\Users\Frede\anaconda3\envs\BioTon\python.exe",
    [string]$Settings = "",
    [switch]$SkipEnvironmentSetup,
    [switch]$SkipMount,
    [switch]$SkipHorekaBootstrap,
    [switch]$PublishToLsdf
)

# Minimal local refresh for the primary master table.  It deliberately omits
# media, Sentinel-2, HOSTRADA and bioacoustic processing.
$ErrorActionPreference = "Stop"
# PowerShell 7 otherwise turns any stderr output of a native process into a
# terminating NativeCommandError.  Step 2 deliberately emits an informational
# warning when it uses its safe Windows single-process fallback.
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSNativeCommandUseErrorActionPreference = $false
}

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
$EnvironmentRoot = [Environment]::ExpandEnvironmentVariables([string]$LocalSettings.environment_dir)
if (-not $EnvironmentRoot) { $EnvironmentRoot = "D:\BioOTon_envs" }
$CorePython = Join-Path $EnvironmentRoot "core\Scripts\python.exe"

if (-not $SkipEnvironmentSetup) {
    & (Join-Path $LocalRoot "setup_local_env.ps1") `
        -BasePython $BasePython -Settings $Settings -SkipBacpipe
    if ($LASTEXITCODE -ne 0) { throw "Lokales Core-Environment konnte nicht eingerichtet werden." }
}
if (-not (Test-Path -LiteralPath $CorePython)) {
    throw "Core Python fehlt: $CorePython"
}

if (-not $SkipMount) {
    & $CorePython (Join-Path $LocalRoot "mount_lsdf.py") --settings $Settings
    if ($LASTEXITCODE -ne 0) { throw "LSDF konnte nicht eingebunden werden." }
}

# Never calculate against stale remote products while a Horeka workflow owns
# the shared output area.  The user must let its unlock job run or release a
# cancelled workflow's lock before starting locally.
$MountDrive = ([string]$LocalSettings.mount_drive).TrimEnd([char[]]@(':', '\', '/')) + ':'
$RemoteLock = Join-Path (Join-Path ($MountDrive + '\\') "Data_automatisation_skripts\outputs") "step_0_control\pipeline.lock"
if (Test-Path -LiteralPath $RemoteLock) {
    throw "Aktiver Horeka-Pipeline-Lock gefunden: $RemoteLock. Nicht parallel ausfuehren."
}

$Workspace = [Environment]::ExpandEnvironmentVariables([string]$LocalSettings.workspace_dir)
$LocalOutputRoot = Join-Path $Workspace "outputs"
$LocalMaster = Join-Path $LocalOutputRoot "Bio_O_Ton_Master.csv"
if (-not $SkipHorekaBootstrap) {
    # Copy exactly one baseline file.  Step 7 uses it to retain already
    # validated non-metadata/non-Step-2 domain values; no output tree is mirrored.
    $RemoteOutputRoot = Join-Path ($MountDrive + '\\') "Data_automatisation_skripts\outputs"
    $RemoteMaster = Join-Path $RemoteOutputRoot "Bio_O_Ton_Master.csv"
    if (-not (Test-Path -LiteralPath $RemoteMaster)) {
        throw "Horeka-Mastertabelle fehlt: $RemoteMaster"
    }
    New-Item -ItemType Directory -Path $LocalOutputRoot -Force | Out-Null
    Copy-Item -LiteralPath $RemoteMaster -Destination $LocalMaster -Force
    Write-Host "Nur Master-Basis kopiert: $LocalMaster"
}
if (-not (Test-Path -LiteralPath $LocalMaster)) {
    throw "Lokale Master-Basis fehlt: $LocalMaster"
}

$GeneratedConfig = Join-Path $LocalRoot "config.local.generated.json"
& $CorePython (Join-Path $LocalRoot "prepare_local_config.py") `
    --settings $Settings `
    --source-config (Join-Path $RepoRoot "config.horeka.json") `
    --output-config $GeneratedConfig `
    --repo-root $RepoRoot `
    --device cpu `
    --minimal-master-refresh
if ($LASTEXITCODE -ne 0) { throw "Lokale Konfiguration konnte nicht erzeugt werden." }

$LogDir = Join-Path $Workspace "outputs\step_0_local_logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Stamp = Get-Date -Format "yyyyMMddTHHmmss"
$RunId = "local_master_refresh_${Stamp}_$PID"
$LockTool = Join-Path $RepoRoot "tools\pipeline_lock.py"

function Invoke-RefreshStep {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$Script,
        [int]$Cpus = 1,
        [string[]]$ExtraArguments = @()
    )

    Write-Host "START $Label"
    $previousCpus = $env:SLURM_CPUS_PER_TASK
    $previousSlurmJob = $env:SLURM_JOB_ID
    $env:SLURM_CPUS_PER_TASK = [string]([Math]::Max(1, $Cpus))
    # Step 2 uses this variable solely to distinguish a managed multi-core
    # execution from an accidental interactive run.  Windows PowerShell 5
    # promotes its informational stderr warning to a terminating error, so
    # identify this deliberate local workflow explicitly.
    $env:SLURM_JOB_ID = "local_master_refresh_$PID"
    try {
        & $CorePython (Join-Path $RepoRoot $Script) --config $GeneratedConfig @ExtraArguments `
            1> (Join-Path $LogDir "${Stamp}_${Label}.out") `
            2> (Join-Path $LogDir "${Stamp}_${Label}.err")
        if ($LASTEXITCODE -ne 0) { throw "$Label fehlgeschlagen. Details: $LogDir" }
    }
    finally {
        $env:SLURM_CPUS_PER_TASK = $previousCpus
        $env:SLURM_JOB_ID = $previousSlurmJob
    }
}

function Start-RefreshStep {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$Script,
        [int]$Cpus = 1,
        [string[]]$ExtraArguments = @()
    )

    $stdout = Join-Path $LogDir "${Stamp}_${Label}.out"
    $stderr = Join-Path $LogDir "${Stamp}_${Label}.err"
    return Start-Job -Name $Label -ScriptBlock {
        param($Python, $Repo, $Config, $TargetScript, $AllocatedCpus, $Extra, $OutFile, $ErrFile, $LocalJobId)
        Set-Location $Repo
        $env:SLURM_CPUS_PER_TASK = [string]([Math]::Max(1, $AllocatedCpus))
        $env:SLURM_JOB_ID = $LocalJobId
        & $Python (Join-Path $Repo $TargetScript) --config $Config --force @Extra 1> $OutFile 2> $ErrFile
        [int]$LASTEXITCODE
    } -ArgumentList $CorePython, $RepoRoot, $GeneratedConfig, $Script, $Cpus, $ExtraArguments, $stdout, $stderr, "local_master_refresh_$PID"
}

function Complete-RefreshStep {
    param([Parameter(Mandatory = $true)]$Job)
    Wait-Job -Job $Job | Out-Null
    $exitCodes = @(Receive-Job -Job $Job)
    Remove-Job -Job $Job -Force
    if ($exitCodes.Count -ne 1 -or [int]$exitCodes[0] -ne 0) {
        throw "$($Job.Name) fehlgeschlagen. Details: $LogDir"
    }
    Write-Host "DONE  $($Job.Name)"
}

$LockAcquired = $false
try {
    & $CorePython $LockTool --config $GeneratedConfig acquire --run-id $RunId --owner-pid $PID
    if ($LASTEXITCODE -ne 0) { throw "Lokaler Pipeline-Lock konnte nicht gesetzt werden." }
    $LockAcquired = $true

    # Step 1 applies country = Germany and removes non-German IDs from the
    # local metadata snapshot.  The global formation products must then be
    # rebuilt from the configured no_K_post2017 GeoPackage.
    Invoke-RefreshStep -Label "step_1_metadata" -Script "scripts\Step_1_metadata_extraction.py" -Cpus 2
    Invoke-RefreshStep -Label "step_2_0" -Script "scripts\Step_2_0_clean_lrts.py" -Cpus ([int]$LocalSettings.logical_cpus) -ExtraArguments @("--force")
    Invoke-RefreshStep -Label "step_2_1" -Script "scripts\Step_2_1_merge_lrts_and_grid.py" -Cpus ([int]$LocalSettings.logical_cpus) -ExtraArguments @("--force")

    # Step 2.4 is scoped to the recording cells emitted by Step 2.2. This avoids
    # creating a nationwide 10 m product solely to refresh the master table.
    $step22 = Start-RefreshStep -Label "step_2_2" -Script "scripts\Step_2_2_assign_points_to_lrt_grid.py" -Cpus 2
    Complete-RefreshStep -Job $step22
    $LocalConfig = Get-Content -Raw -LiteralPath $GeneratedConfig | ConvertFrom-Json
    $PointAssignments = [string]$LocalConfig.point_lrt_assignment.output_csv
    $step24 = Start-RefreshStep -Label "step_2_4" -Script "scripts\Step_2_4_generate_10m_formation_status_products.py" -Cpus ([int]$LocalSettings.logical_cpus) -ExtraArguments @("--grid-ids-file", $PointAssignments)
    Complete-RefreshStep -Job $step24

    Invoke-RefreshStep -Label "step_7_0" -Script "scripts\Step_7_0_update_master_table.py" -Cpus 2 -ExtraArguments @("--preserve-existing-nonformation-domains")

    $MasterCsv = Join-Path $Workspace "outputs\Bio_O_Ton_Master.csv"
    if (-not (Test-Path -LiteralPath $MasterCsv)) { throw "Mastertabelle wurde nicht erzeugt: $MasterCsv" }
    Write-Host "Mastertabelle: $MasterCsv"

    if ($PublishToLsdf) {
        & $CorePython (Join-Path $LocalRoot "publish_local_outputs.py") `
            --settings $Settings --repo-root $RepoRoot
        if ($LASTEXITCODE -ne 0) { throw "Lokale Outputs konnten nicht auf LSDF veroeffentlicht werden." }
    }
}
finally {
    if ($LockAcquired) {
        & $CorePython $LockTool --config $GeneratedConfig release --run-id $RunId
    }
}
