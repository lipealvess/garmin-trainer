#!/usr/bin/env bash
# Execucao agendada no Linux (chamada pelo timer do systemd a cada 30 min e ao ligar o PC).
# Equivalente ao run_pipeline.ps1 do Windows: analisa atividades novas e envia o relatorio
# matinal uma vez por dia. Nunca gera nem publica treinos (quem faz isso e o Greg).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
LOG_DIR="$ROOT/data/logs"
mkdir -p "$LOG_DIR"
export PYTHONIOENCODING=utf-8

# Evita duas execucoes simultaneas (ex: timer + execucao manual) mexendo no mesmo state.json.
exec 9>"$ROOT/data/.tick.lock"
flock -n 9 || { echo "Outra execucao em andamento, saindo."; exit 0; }

# Logo apos ligar/acordar o PC a rede pode ainda nao estar de pe. Sem rede nao e falha:
# so sai, e a proxima execucao (30 min) tenta de novo.
for _ in $(seq 1 24); do
    getent hosts connect.garmin.com >/dev/null 2>&1 && break
    sleep 5
done
if ! getent hosts connect.garmin.com >/dev/null 2>&1; then
    echo "$(date '+%F %T') sem rede, pulando." >> "$LOG_DIR/tick_$(date +%Y%m%d).log"
    exit 0
fi

RUN_LOG="$(mktemp)"
trap 'rm -f "$RUN_LOG"' EXIT

"$PY" -m garmin_trainer.cli tick > "$RUN_LOG" 2>&1
EXIT_CODE=$?

{
    echo "===== $(date '+%F %T') (exit $EXIT_CODE) ====="
    cat "$RUN_LOG"
} >> "$LOG_DIR/tick_$(date +%Y%m%d).log"

if [ "$EXIT_CODE" -ne 0 ]; then
    "$PY" -m garmin_trainer.cli notify-failure --log-file "$RUN_LOG" >> "$LOG_DIR/tick_$(date +%Y%m%d).log" 2>&1
fi

# Mantem so 30 dias de logs.
find "$LOG_DIR" -name 'tick_*.log' -mtime +30 -delete 2>/dev/null

exit "$EXIT_CODE"
