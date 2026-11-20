$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$PyCandidates = @(
    (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
) | Where-Object { $_ -and (Test-Path $_) -and ($_ -notlike "*\WindowsApps\python*") }

if (-not $PyCandidates -or $PyCandidates.Count -eq 0) {
    Write-Error "Python 3.11+ not found. Please install Python 3.11+ from python.org first."
    exit 1
}

$Py = $PyCandidates[0]
& $Py (Join-Path $ScriptDir "install.py") @args
