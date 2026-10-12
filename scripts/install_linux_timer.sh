#!/usr/bin/env bash
# Instala (ou reinstala) o agendamento do garmin-trainer como timer do systemd do usuario.
#   - roda 2 min depois de ligar o PC / fazer login, e depois a cada 30 min;
#   - Persistent=true: execucoes perdidas com o PC desligado/suspenso rodam assim que ele volta.
# Uso: scripts/install_linux_timer.sh          (instala e ativa)
#      scripts/install_linux_timer.sh --remove (desativa e remove)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
NAME="garmin-trainer"

if [ "${1:-}" = "--remove" ]; then
    systemctl --user disable --now "$NAME.timer" 2>/dev/null || true
    rm -f "$UNIT_DIR/$NAME.service" "$UNIT_DIR/$NAME.timer" "$UNIT_DIR/$NAME-alert.service"
    systemctl --user daemon-reload
    echo "Timer removido."
    exit 0
fi

[ -x "$ROOT/.venv/bin/python" ] || { echo "Crie o .venv antes: python3 -m venv .venv && .venv/bin/pip install -e ."; exit 1; }
mkdir -p "$UNIT_DIR"

# Os scripts sao chamados via /bin/bash (e nao direto) para nao depender do bit +x, que ja se
# perdeu uma vez neste repo (veio do Windows) e deixou o timer falhando em silencio com 203/EXEC.
cat > "$UNIT_DIR/$NAME.service" <<EOF
[Unit]
Description=garmin-trainer: analise de atividades e relatorio matinal do Garmin
Wants=network-online.target
After=network-online.target
OnFailure=$NAME-alert.service

[Service]
Type=oneshot
ExecStart=/bin/bash "$ROOT/scripts/run_tick.sh"
WorkingDirectory=$ROOT
TimeoutStartSec=15min
Nice=10
EOF

cat > "$UNIT_DIR/$NAME-alert.service" <<EOF
[Unit]
Description=garmin-trainer: email de alerta quando a execucao agendada falha

[Service]
Type=oneshot
ExecStart=/bin/bash "$ROOT/scripts/notify_failure.sh"
WorkingDirectory=$ROOT
EOF

cat > "$UNIT_DIR/$NAME.timer" <<EOF
[Unit]
Description=garmin-trainer a cada 30 min e ao ligar o PC

[Timer]
OnStartupSec=2min
OnCalendar=*:0/30
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now "$NAME.timer"

# Com "linger", o timer roda mesmo antes de voce fazer login (ex: PC ligado na tela de login).
if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]; then
    loginctl enable-linger "$USER" 2>/dev/null \
        && echo "Linger ativado: o timer roda mesmo sem sessao aberta." \
        || echo "Aviso: nao consegui ativar linger (rode: sudo loginctl enable-linger $USER). Sem isso, o timer so roda com voce logado."
fi

echo
systemctl --user list-timers "$NAME.timer" --no-pager
echo
echo "Logs: $ROOT/data/logs/tick_AAAAMMDD.log  |  journalctl --user -u $NAME.service"
