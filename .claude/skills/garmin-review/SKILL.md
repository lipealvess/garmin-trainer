---
name: garmin-review
description: Analise retrospectiva das ultimas N atividades do Garmin, como personal trainer (o que evoluiu, pontos de atencao, leitura de recuperacao e peso). Nunca propoe treinos - quem monta o plano e' o treinador Greg via Garmin Coach.
---

# garmin-review

Puxa as ultimas N atividades de corrida do Garmin Connect (default 5) e os dados de sono/estresse/HRV/
peso do mesmo periodo, e pede pra IA uma analise retrospectiva no papel de personal trainer: o que
evoluiu (pace, FC, controle de deriva cardiaca, consistencia), pontos de atencao, e como a recuperacao/
peso se relacionam com os treinos.

## Contexto

Desde 2026-09-13 o atleta tem um treinador humano (Greg) montando os treinos dele via Garmin Coach.
Este sistema (garmin-trainer) nao prescreve mais treinos — o papel dele e monitorar e analisar. Esta
skill e o modo "sob demanda" desse acompanhamento (o modo automatico/diario e a skill `garmin-pipeline`,
que roda o check-in todo dia).

## Passos

1. Rode: `.venv/bin/python -m garmin_trainer.cli review --limit 5`
   (use `--limit N` se o usuario pedir um numero diferente de atividades)
2. Apresente ao usuario: resumo, o que evoluiu, pontos de atencao, e a leitura de recuperacao/peso.
3. Se o usuario pedir pra receber por email, adicione `--email`.
4. Nunca transforme essa analise em uma proposta de treinos futuros — se o usuario pedir sugestoes de
   treino, lembre que quem decide isso e o Greg; no maximo aponte o que os dados sugerem (ex: "a FC
   sugere que esse pace ainda esta puxado"), sem prescrever series/paces/volumes.
