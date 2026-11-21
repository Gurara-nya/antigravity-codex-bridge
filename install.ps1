$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Test-Python311Plus {
    param([string]$ExePath)
    if (-not $ExePath -or -not (Test-Path $ExePath) -or ($ExePath -like "*\WindowsApps\python*")) {
        return $false
    }
    try {
        $prevPref = $ErrorActionPreference
        $ErrorActionPreference = "SilentlyContinue"
        & $ExePath -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" *> $null
        $code = $LASTEXITCODE
        $ErrorActionPreference = $prevPref
        return ($code -eq 0)
    } catch {
        return $false
    }
}

$RawCandidates = New-Object System.Collections.Generic.List[string]

# 1. All `python` / `python3` entries in PATH
Get-Command python, python3 -All -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.Source) { [void]$RawCandidates.Add($_.Source) }
}

# 2. Windows Python Launcher (`py.exe`) for 3.13, 3.12, 3.11
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($verFlag in @("-3.13", "-3.12", "-3.11", "-3")) {
        try {
            $pyOut = & py $verFlag -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $pyOut) {
                $pyPath = ($pyOut | Select-Object -Last 1).ToString().Trim()
                if ($pyPath) { [void]$RawCandidates.Add($pyPath) }
            }
        } catch {}
    }
}

# 3. Standard per-user and system-wide Python 3.11+ install directories (newest first)
foreach ($root in @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles", "${env:ProgramFiles(x86)}")) {
    if ($root -and (Test-Path $root)) {
        Get-ChildItem -Path $root -Directory -Filter "Python3*" -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object {
                $exe = Join-Path $_.FullName "python.exe"
                if (Test-Path $exe) { [void]$RawCandidates.Add($exe) }
            }
    }
}

$SelectedPy = $null
$Seen = @{}
foreach ($cand in $RawCandidates) {
    $norm = $cand.ToLowerInvariant()
    if ($Seen.ContainsKey($norm)) { continue }
    $Seen[$norm] = $true
    if (Test-Python311Plus -ExePath $cand) {
        $SelectedPy = $cand
        break
    }
}

if (-not $SelectedPy) {
    Write-Error "未找到可用的 Python 3.11+ 解释器（已跳过版本过低或不可用的 Python）。请先从 https://www.python.org/downloads/ 安装 Python 3.11+ 后重试。"
    exit 1
}

& $SelectedPy (Join-Path $ScriptDir "install.py") @args
exit $LASTEXITCODE
