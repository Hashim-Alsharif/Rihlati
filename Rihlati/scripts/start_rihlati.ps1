param([switch]$NoBrowser)

# Start only this local project. No global settings, scheduled tasks, or installs.
$ErrorActionPreference = 'Stop'
$rihlatiRoot = Split-Path -Parent $PSScriptRoot
$rihlatiUrl = 'http://localhost:8080/'

# Some developer hosts supply both Path and PATH. Windows PowerShell's
# Start-Process rejects that duplicate case-insensitive key. Normalize ONLY
# this process environment; never change User/Machine environment settings.
$rihlatiEnvironment = [Environment]::GetEnvironmentVariables('Process')
$rihlatiPathNames = @($rihlatiEnvironment.Keys | Where-Object { $_ -ieq 'Path' })
if ($rihlatiPathNames.Count -gt 1) {
    $rihlatiPathParts = @($rihlatiPathNames | ForEach-Object { $rihlatiEnvironment[$_] -split ';' } | Where-Object { $_ } | Select-Object -Unique)
    foreach ($rihlatiPathName in $rihlatiPathNames) {
        [Environment]::SetEnvironmentVariable($rihlatiPathName, $null, 'Process')
    }
    [Environment]::SetEnvironmentVariable('Path', ($rihlatiPathParts -join ';'), 'Process')
}

function Get-RihlatiHealth {
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/health' -TimeoutSec 1 -ErrorAction Stop
        if ($health.app -eq 'rihlati' -and $health.status -eq 'ok') { return $health }
    } catch { }
    return $null
}

function Test-LocalPort {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $pending = $client.BeginConnect('127.0.0.1', 8080, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne(500)) { return $false }
        $client.EndConnect($pending)
        return $true
    } catch { return $false }
    finally { $client.Close() }
}

try {
    if (Get-RihlatiHealth) {
        Write-Host "Rihlati is already running: $rihlatiUrl"
        if (-not $NoBrowser) { Start-Process $rihlatiUrl }
        exit 0
    }
    if (Test-LocalPort) {
        throw 'Port 8080 is occupied by an unrecognized or unresponsive service. Nothing was stopped. Ask for help identifying that process.'
    }

    $runtimeRoot = $env:RIHLATI_RUNTIME
    if (-not $runtimeRoot) {
        $runtimeRoot = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'
    }
    $candidates = @(
        $env:RIHLATI_PYTHON
        (Join-Path $rihlatiRoot '.venv\Scripts\python.exe')
        (Join-Path $runtimeRoot 'python\python.exe')
    )
    $systemPython = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($systemPython) { $candidates += $systemPython.Source }
    $pythonExe = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
    if (-not $pythonExe) {
        throw 'Python was not found. Install Python 3.12 with pypdf, or set RIHLATI_PYTHON to your Python executable.'
    }
    & $pythonExe -c 'import sqlite3, pypdf, flask, waitress, argon2, dotenv, PIL' 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Install the project requirements.txt in .venv first. See README.md. Python: $pythonExe"
    }

    $logFolder = Join-Path $rihlatiRoot 'data\logs'
    New-Item -ItemType Directory -Path $logFolder -Force | Out-Null
    $logStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $outputLog = Join-Path $logFolder "server-$logStamp.log"
    $errorLog = Join-Path $logFolder "server-$logStamp.error.log"
    $server = Start-Process -FilePath $pythonExe -ArgumentList @('-u', 'scripts/api_server.py') `
        -WorkingDirectory $rihlatiRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $outputLog -RedirectStandardError $errorLog

    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    do {
        if (Get-RihlatiHealth) {
            Write-Host "Rihlati is ready: $rihlatiUrl"
            Write-Host "Server PID: $($server.Id)"
            Write-Host "Logs: $logFolder"
            Write-Host 'Run Start-Rihlati.cmd again after restarting your computer.'
            if (-not $NoBrowser) { Start-Process $rihlatiUrl }
            exit 0
        }
        $server.Refresh()
        if ($server.HasExited) { throw "The server exited. See: $errorLog" }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "The server did not become ready within 20 seconds. It may still be starting. See: $errorLog"
} catch {
    Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
