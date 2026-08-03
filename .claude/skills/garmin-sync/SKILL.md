---
name: garmin-sync
description: Sincroniza e resume as atividades recentes do Garmin Connect, sem chamar a IA nem alterar nada.
---

# garmin-sync

Puxa as atividades novas do Garmin Connect desde a ultima sincronizacao registrada e mostra um resumo
de metricas (distancia, duracao, FC media/max, pace, training effect). Nao chama a IA e nao modifica
nada no Garmin ou no perfil do atleta — e apenas leitura.

## Passos

1. Rode: `./.venv/Scripts/python.exe -m garmin_trainer.cli sync`
2. Se pedir MFA, peça o codigo ao usuario.
3. Apresente a tabela de atividades retornada de forma legivel.
4. Se nao houver atividades novas, informe isso claramente (nao e um erro).

Se o comando falhar por falta de configuracao (.env ausente ou incompleto), acione a skill
garmin-setup em vez de tentar contornar o erro.
