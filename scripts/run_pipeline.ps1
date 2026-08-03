$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$logDir = Join-Path $root "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "pipeline_$timestamp.log"
$planFile = Join-Path $root "data\plans\plan_$timestamp.json"

& "$root\.venv\Scripts\python.exe" -m garmin_trainer.cli run --push --email --json-out "$planFile" *> "$logFile"

exit $LASTEXITCODE
