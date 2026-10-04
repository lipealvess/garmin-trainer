---
name: garmin-pipeline
description: Roda o acompanhamento automatizado (analisa cada atividade nova e envia o relatorio matinal de sono/HRV/FC/estresse/body battery) — o fluxo fim-a-fim do garmin-trainer. NAO gera nem publica treinos.
---

# garmin-pipeline

O acompanhamento tem dois tipos de email, ambos em HTML:

- **Por atividade**: cada atividade nova no Garmin Connect vira um email com a analise do treino
  (prescrito pelo Greg x executado, voltas, tempo por zona, desacoplamento pace:FC/deriva cardiaca,
  cadencia, calor).
- **Relatorio matinal** (1x por dia): sono e fases, HRV x faixa normal, FC de repouso x media 7d,
  body battery, estresse/passos/intensidade de ontem, tendencias de 7 dias, contagem regressiva da
  prova e previsao do Garmin. Sai assim que o sono da noite sincroniza (ou a partir das 11h).

## Mudanca de rota (2026-09-13)

Desde 2026-09-13 quem monta o plano de treinos do atleta e' o **treinador Greg, via Garmin Coach** —
nao mais este pipeline. Por isso este fluxo **NUNCA gera nem publica treinos** (sem `--push`, sem
`generate_coach_plan`). O papel do garmin-trainer virou monitoramento/analise, nao prescricao. Ver
`config/athlete_profile.yaml` -> `external_coach`.

Os comandos antigos de plano (`coach`, `run --push`) ainda existem no CLI mas sao manuais/opcionais —
ver a skill `garmin-coach`. Nunca rode `--push` por conta propria: publicaria treinos que colidem com
o calendario que o Greg ja preencheu.

## Automacao ja configurada (Linux, desde 2026-10-04)

Roda sozinho via **timer do systemd do usuario** (`garmin-trainer.timer` -> `scripts/run_tick.sh` ->
`cli tick`): 2 min apos ligar o PC e a cada 30 min, com `Persistent=true` (recupera execucoes perdidas
com o PC desligado/suspenso) e linger ativado. Sem novidade, o `tick` nao chama a IA nem manda email.
Instalar/reinstalar: `scripts/install_linux_timer.sh` (`--remove` para tirar). O estado (ultima
atividade analisada, data do ultimo relatorio, ultimo alerta de falha) fica em `data/state.json`.

Esta skill serve pra rodar manualmente sob demanda ou debugar — nao para configurar automacao nova.

## Passos

1. Para forcar o relatorio matinal agora (mesmo se ja enviado hoje) + analisar atividades novas:
   `.venv/bin/python -m garmin_trainer.cli daily`
   Para so ver no terminal, sem email e sem avancar o estado: adicione `--no-email`.
   Para rodar exatamente o que o timer roda: `.venv/bin/python -m garmin_trainer.cli tick`.
2. A analise da IA e best-effort: se o Gemini falhar (ha fallback entre modelos), o email ainda sai
   so com as metricas — reporte isso, mas nao trate como falha total.
3. Reporte de forma curta: houve atividade nova? qual a prontidao do dia e o headline de cada email.
4. Se o comando falhar de verdade (login, MFA interativo), pare e reporte o erro — nao re-tente em loop.
   MFA interativo trava a execucao agendada; se acontecer, avise o usuario para rodar `login-test`.
5. Se o usuario disser que o email nao chegou: veja `systemctl --user list-timers garmin-trainer.timer`,
   `journalctl --user -u garmin-trainer.service` e `data/logs/tick_AAAAMMDD.log`. Falhas mandam no
   maximo um email de alerta por dia.
