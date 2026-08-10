param(
    [string]$Settings = "",
    [switch]$Apply
)

$ErrorActionPreference = "Stop"
$LocalRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Settings) { $Settings = Join-Path $LocalRoot "local.settings.json" }

$LocalSettings = Get-Content -Raw -LiteralPath $Settings | ConvertFrom-Json
$Workspace = [IO.Path]::GetFullPath(
    [Environment]::ExpandEnvironmentVariables([string]$LocalSettings.workspace_dir)
)
$Outputs = Join-Path $Workspace "outputs"
$Lock = Join-Path $Outputs "step_0_control\pipeline.lock"
if (Test-Path -LiteralPath $Lock) {
    throw "Aktiver lokaler Pipeline-Lock: $Lock. Lauf zuerst mit Ctrl+C beenden."
}

$MountDrive = [string]$LocalSettings.mount_drive
if (-not $MountDrive) { $MountDrive = "L:" }
$MountRoot = $MountDrive.TrimEnd("\", "/") + "\"
$RemoteRelative = [string]$LocalSettings.horeka_outputs_relative
if (-not $RemoteRelative) { $RemoteRelative = "Data_automatisation_skripts/outputs" }
$RemoteOutputs = Join-Path $MountRoot ($RemoteRelative.Replace("/", "\"))
if (-not (Test-Path -LiteralPath $RemoteOutputs -PathType Container)) {
    throw "Horeka-Outputordner ist nicht lesbar: $RemoteOutputs"
}

# Nur grosse Payloads entfernen. Kleine States, Inventare, Logs und QC-Berichte
# bleiben lokal, damit Mastertable, Planung und Diagnose weiter funktionieren.
$RelativeTargets = @(
    "step_5_2_weather_download\hostrada_cache",
    "step_5_3_hostrada_monthly_download\netcdf",
    "step_5_4_hostrada_raster_products"
)

$VerifiedFiles = 0
[Int64]$VerifiedBytes = 0
$PresentTargets = @()

foreach ($RelativeTarget in $RelativeTargets) {
    $LocalTarget = Join-Path $Outputs $RelativeTarget
    if (-not (Test-Path -LiteralPath $LocalTarget -PathType Container)) { continue }

    $RemoteTarget = Join-Path $RemoteOutputs $RelativeTarget
    $LocalFiles = @(Get-ChildItem -LiteralPath $LocalTarget -Recurse -Force -File)
    foreach ($LocalFile in $LocalFiles) {
        $RelativeFile = $LocalFile.FullName.Substring($LocalTarget.Length).TrimStart("\")
        $RemoteFile = Join-Path $RemoteTarget $RelativeFile
        if (-not (Test-Path -LiteralPath $RemoteFile -PathType Leaf)) {
            throw "Remote-Datei fehlt; lokales Cleanup abgebrochen: $RemoteFile"
        }
        $RemoteInfo = Get-Item -LiteralPath $RemoteFile
        if ($RemoteInfo.Length -ne $LocalFile.Length) {
            throw "Groessenabweichung; lokales Cleanup abgebrochen: $($LocalFile.FullName)"
        }
        $VerifiedFiles += 1
        $VerifiedBytes += $LocalFile.Length
    }
    $PresentTargets += $LocalTarget
}

$Summary = [PSCustomObject]@{
    Mode = if ($Apply) { "apply" } else { "dry_run" }
    VerifiedFiles = $VerifiedFiles
    VerifiedGiB = [Math]::Round($VerifiedBytes / 1GB, 2)
    Targets = $PresentTargets.Count
    RemoteOutputs = $RemoteOutputs
}
$Summary | Format-List

if (-not $Apply) {
    Write-Host "Nur geprueft. Zum verifizierten Entfernen erneut mit -Apply starten."
    exit 0
}

foreach ($LocalTarget in $PresentTargets) {
    Remove-Item -LiteralPath $LocalTarget -Recurse -Force
    Write-Host "LOKAL ENTFERNT: $LocalTarget"
}

Write-Host "Cleanup abgeschlossen. Die Dateien bleiben auf Horeka/LSDF erhalten."
