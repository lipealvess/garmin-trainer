$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$logDir = Join-Path $root "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "pipeline_$timestamp.log"

# Python escreve UTF-8; sem isso, acentos saem corrompidos no log ao passar pelo redirect do PowerShell.
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

# EAP="Continue" durante a chamada nativa: com "Stop", qualquer linha que o python escreva
# no stderr (inclusive um traceback) e' promovida a erro terminante pelo PowerShell 5.1,
# abortando o script antes do conteudo ser gravado no log -- e' por isso que falhas viravam
# logs vazios de 0 bytes. O exit code ja e' checado explicitamente abaixo, sem depender do EAP.
#
# Desde 2026-09-13: o treinador Greg (Garmin Coach) e' quem monta o plano de treinos do
# atleta, entao o pipeline automatico NAO gera nem publica treinos (`--push` removido).
# So faz o check-in diario: sincroniza, comenta metricas do dia e analisa o treino do dia
# se houve um.
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& "$root\.venv\Scripts\python.exe" -m garmin_trainer.cli tick *> "$logFile"
$exitCode = $LASTEXITCODE
$ErrorActionPreference = $prevEAP

if ($exitCode -ne 0) {
    $ErrorActionPreference = "Continue"
    & "$root\.venv\Scripts\python.exe" -m garmin_trainer.cli notify-failure --log-file "$logFile" *>> "$logFile"
    $ErrorActionPreference = $prevEAP
}

exit $exitCode
