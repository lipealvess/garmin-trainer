#!/usr/bin/env bash
# Chamado pelo systemd (OnFailure) quando garmin-trainer.service falha. Cobre falhas que acontecem
# antes do run_tick.sh rodar (ex: 203/EXEC), que nao passam pelo alerta do proprio run_tick.sh.
# O notify-failure limita a um email por dia.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$(mktemp)"
trap 'rm -f "$LOG"' EXIT

journalctl --user -u garmin-trainer.service -n 40 --no-pager > "$LOG" 2>&1
"$ROOT/.venv/bin/python" -m garmin_trainer.cli notify-failure --log-file "$LOG"
