---
name: garmin-coach
description: (Manual/opcional desde 2026-09-13 — o treinador Greg via Garmin Coach e' quem monta o plano oficial) Roda a IA (Gemini) sobre atividades, sono, estresse e HRV recentes do Garmin e propoe um bloco de treinos alternativo, com revisao antes de publicar.
---

# garmin-coach

Gera um bloco de treinos alternativo com base no historico recente de atividades, sono/estresse/HRV
dos ultimos dias, e no perfil do atleta (`config/athlete_profile.yaml`). Por padrao roda em modo
dry-run — nao escreve nada no Garmin Connect. A IA usa os dados de recuperacao (sono, estresse, HRV)
para de fato ajustar a intensidade do bloco quando necessario, nao so pra comentar — isso aparece no
campo `recovery_assessment` da resposta.

## Atencao: desde 2026-09-13 o plano oficial e' do treinador Greg (Garmin Coach)

O atleta tem um treinador humano (Greg) montando os treinos dele via Garmin Coach. Esta skill so deve
ser usada se o usuario pedir **explicitamente** um plano/segunda opiniao gerado por IA — nao rode por
iniciativa propria, e nunca use `--push` sem confirmar que o usuario entende que isso vai **competir
com o calendario que o Greg ja preencheu** no Garmin Connect (workouts duplicados/conflitantes no
mesmo dia). Pra acompanhamento normal do dia a dia, a automacao usa a skill `garmin-pipeline`
(check-in diario, sem gerar treinos) e a skill `garmin-review` (analise retrospectiva sob demanda).

## Passos

1. Rode em dry-run primeiro:
   `.venv/bin/python -m garmin_trainer.cli coach`
2. Mostre ao usuario a analise da IA, o que melhorou, pontos de atencao, avaliacao de recuperacao
   (sono/estresse/HRV) e a lista de treinos propostos (data, esporte, nome, descricao).
3. Pergunte explicitamente se o usuario quer publicar esses treinos no Garmin Connect antes de fazer
   qualquer envio. Publicar cria e agenda workouts na conta real do usuario — isso e uma acao que
   afeta um sistema externo, entao sempre confirme antes, mesmo que o usuario ja tenha confirmado em
   uma execucao anterior.
4. Se o usuario confirmar, rode:
   `.venv/bin/python -m garmin_trainer.cli coach --push`
5. Se o usuario tambem quiser o email de insights nesta execucao manual, adicione `--email`.

Use `--days-ahead N` se o usuario quiser um horizonte de planejamento diferente de 7 dias.
