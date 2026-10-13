param(
    [Parameter(Mandatory=$true)]
    [string]$RawDir
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

New-Item -ItemType Directory -Force -Path ".\logs" | Out-Null
New-Item -ItemType Directory -Force -Path ".\output" | Out-Null

$logPath = Join-Path $PSScriptRoot "logs\extract_latest.log"
$outputPath = Join-Path $PSScriptRoot "output\research_pre2025.sqlite3"
$scriptPath = Join-Path $PSScriptRoot "extract_research.py"

$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    $exe = $pyLauncher.Source
    $prefix = @("-3")
} else {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        Write-Host "FAIL: Python 3 was not found." -ForegroundColor Red
        exit 3
    }
    $exe = $python.Source
    $prefix = @()
}

Write-Host "Research source: $RawDir"
Write-Host "Output database: $outputPath"
Write-Host "Log: $logPath"
Write-Host "HOLDOUT FIREWALL: 2025.tar and 2026.tar are not accessed."
Write-Host ""

$arguments = @()
$arguments += $prefix
$arguments += @(
    "-u",
    $scriptPath,
    "--raw-dir", $RawDir,
    "--output", $outputPath
)

& $exe @arguments 2>&1 | Tee-Object -FilePath $logPath
$rc = $LASTEXITCODE

Write-Host ""
Write-Host "Python exit code: $rc"
exit $rc
