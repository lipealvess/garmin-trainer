---
name: garmin-coach
description: Gera (e opcionalmente publica no relogio) o plano de treinos da semana com a IA, a partir do perfil, das ultimas 4 semanas de atividades e de 7 dias de sono/HRV/FC. O garmin-trainer e' o dono do plano desde 2026-10-12.
---

# garmin-coach

Monta o plano semanal (`cli plan`). O planejador recebe o perfil (`config/athlete_profile.yaml`:
objetivo, `training.periodization`, `training.key_rules`, dias preferidos), as atividades das ultimas
4 semanas, 7 dias de recuperacao e o plano da semana anterior, e usa a recuperacao para decidir de
verdade a intensidade (campo `recovery_assessment`).

## Contexto

- Entre 2026-09-13 e 2026-10-11 o plano foi do treinador Greg (Garmin Coach). Desde 2026-10-12 voltou
  a ser do garmin-trainer, a pedido do atleta (`training.plan_owner: garmin_trainer`).
- Rodagens leves e longao sao guiados por faixa de bpm (`hr_range`, Z2 do perfil = 140-155), nao por
  pace: o historico mostrou 73-96% do tempo em Z4/Z5 nas corridas "tranquilas" guiadas por pace.
- Com `training.auto_publish: true`, o timer gera e publica a semana sozinho todo domingo (ou no
  primeiro tick da semana). Esta skill e para rodar sob demanda: replanejar no meio da semana, ver um
  rascunho, ou depois de mudar o perfil.

## Passos

1. Rascunho (nao publica nada):
   `.venv/bin/python -m garmin_trainer.cli plan`
   (`--start-date AAAA-MM-DD` para escolher o inicio; padrao: hoje, ou a segunda se hoje for domingo)
2. Mostre a semana: treinos por dia com os steps, o racional e a leitura de recuperacao.
3. Publicar cria e agenda treinos na conta real e apaga os treinos futuros do plano anterior —
   confirme com o usuario antes, a menos que ele ja tenha pedido para publicar nesta conversa.
4. Para publicar: `.venv/bin/python -m garmin_trainer.cli plan --push --email`
