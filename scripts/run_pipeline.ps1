$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$logDir = Join-Path $root "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "pipeline_$timestamp.log"
$planFile = Join-Path $root "data\plans\plan_$timestamp.json"

# Python escreve UTF-8; sem isso, acentos saem corrompidos no log ao passar pelo redirect do PowerShell.
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

& "$root\.venv\Scripts\python.exe" -m garmin_trainer.cli run --push --email --json-out "$planFile" *> "$logFile"
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    & "$root\.venv\Scripts\python.exe" -m garmin_trainer.cli notify-failure --log-file "$logFile" 2>&1 | Out-Null
}

exit $exitCode
