param([Parameter(Mandatory=$true)][string]$Python)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
. (Join-Path $repo 'scripts_local_run\native_process.ps1')
$testDir = Join-Path ([IO.Path]::GetTempPath()) ('bioton native test ' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $testDir | Out-Null
$stdout = Join-Path $testDir 'stdout.log'
$stderr = Join-Path $testDir 'stderr.log'
$fixture = Join-Path $PSScriptRoot 'native_process_fixture.py'
$values = @('space in path', 'embedded"quote', 'C:\trailing space\', '')
Invoke-LoggedNativeProcess -Executable $Python -Arguments (@($fixture, 'success') + $values) `
    -WorkingDirectory $repo -StdoutPath $stdout -StderrPath $stderr
if ((Get-Content -Raw $stdout) -notmatch 'stdout completed') { throw 'Missing stdout' }
if ((Get-Content -Raw $stderr) -notmatch 'WARNING: outside Slurm') { throw 'Missing stderr' }
$failed = $false
try {
    Invoke-LoggedNativeProcess -Executable $Python -Arguments (@($fixture, 'fail') + $values) `
        -WorkingDirectory $repo -StdoutPath $stdout -StderrPath $stderr
}
catch {
    if ($_.Exception.Message -notmatch 'exit code 7' -or $_.Exception.Message -notmatch 'fixture failure') { throw }
    $failed = $true
}
if (-not $failed) { throw 'Nonzero exit did not terminate the step' }
Write-Host "PASS: PowerShell $($PSVersionTable.PSVersion), stderr, arguments, exit code, failure details. Logs: $testDir"
