---
name: garmin-pipeline
description: Roda o ciclo completo e automatizado (sincroniza Garmin, chama a IA, publica os treinos) — o fluxo fim-a-fim do garmin-trainer.
---

# garmin-pipeline

Executa o pipeline completo: sincroniza atividades novas do Garmin Connect, chama a IA para analisar
e gerar o proximo bloco de treinos, publica/agenda os treinos de volta no Garmin, e envia um email de
insights (o que melhorou, pontos de atencao, metricas/alvos pros proximos treinos).

## Automacao ja configurada

Desde 2026-07-24 isso roda sozinho via **Agendador de Tarefas do Windows** (tarefa
`GarminTrainerPipeline`, script `scripts/run_pipeline.ps1`, a cada 2 dias) — nao pelo Claude Code
`loop`/`schedule` (esses rodam em nuvem ou exigem sessao aberta, e este projeto depende de
credenciais e `.venv` locais). Esta skill serve pra rodar manualmente sob demanda (ex: usuario pede
"roda o pipeline agora") ou pra debugar quando a tarefa agendada falhar — nao para configurar uma
nova automacao do zero.

## Autorizacao permanente de push

O usuario validou o fluxo completo (login, sync, coach, push) contra a conta real, corrigiu o bug dos
alvos de FC/pace, e autorizou que esta skill publique treinos automaticamente no Garmin **sem pedir
confirmacao a cada execucao**. A skill `garmin-coach` chamada manualmente numa conversa continua
pedindo confirmacao antes de `--push` — essa autorizacao vale so pra execucao do pipeline completo.

## Passos

1. Rode: `./.venv/Scripts/python.exe -m garmin_trainer.cli run --push --email --json-out data/plans/plan_$(date +%Y%m%d_%H%M%S).json`
   (omita `--email` se o usuario ainda nao configurou SMTP_USER/SMTP_PASSWORD no `.env`)
2. O pipeline pula sozinho se nao houver atividade nova desde a ultima execucao (evita gastar cota da
   IA e evita duplicar treinos no calendario) — isso e esperado, nao e falha.
3. Reporte de forma curta: quantas atividades novas entraram, resumo da analise da IA, e quantos
   treinos foram publicados/agendados.
4. Se o comando falhar (erro de login, MFA pedido interativamente, erro da API Gemini, ou erro ao
   montar o payload do treino), pare e reporte o erro — nao tente mascarar falhas ou re-tentar em loop.
   MFA interativo especificamente vai travar uma execucao agendada sem sessao ativa; se isso acontecer
   repetidamente, avise o usuario que pode ser necessario desativar o MFA da conta Garmin usada aqui ou
   rodar manualmente quando pedir codigo.
5. Se o usuario relatar que a tarefa agendada nao rodou, verifique `data/logs/` pelos logs mais
   recentes antes de qualquer outra coisa — o horario/resultado da ultima tentativa esta ali.
