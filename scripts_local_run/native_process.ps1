# File redirection happens in the process API, not PowerShell's error stream.
# This also works in Windows PowerShell 5.1 with ErrorActionPreference=Stop.
function ConvertTo-NativeArgument {
    param([AllowEmptyString()][string]$Value)
    '"' + [regex]::Replace(
        [regex]::Replace($Value, '(\\*)"', '$1$1\"'),
        '(\\+)$', '$1$1'
    ) + '"'
}

function Invoke-LoggedNativeProcess {
    param(
        [string]$Executable,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [string]$StdoutPath,
        [string]$StderrPath
    )
    $commandLine = ($Arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' '
    $process = Start-Process -FilePath $Executable -ArgumentList $commandLine `
        -WorkingDirectory $WorkingDirectory -WindowStyle Hidden `
        -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath `
        -PassThru -Wait
    try {
        $code = $process.ExitCode
        if ($null -eq $code) { throw 'Native process did not return an exit code.' }
        if ($code -ne 0) {
            $detail = Get-Content -LiteralPath $StderrPath -Tail 20 -ErrorAction SilentlyContinue
            throw "Python exit code ${code}. Log: $StderrPath`n$($detail -join "`n")"
        }
    }
    finally { $process.Dispose() }
}
