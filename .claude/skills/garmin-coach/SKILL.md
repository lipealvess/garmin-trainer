---
name: garmin-coach
description: Roda a IA (Gemini) sobre atividades, sono, estresse e HRV recentes do Garmin e propoe o proximo bloco de treinos, com revisao antes de publicar.
---

# garmin-coach

Gera o proximo bloco de treinos com base no historico recente de atividades, sono/estresse/HRV dos
ultimos dias, e no perfil do atleta (`config/athlete_profile.yaml`). Por padrao roda em modo dry-run —
nao escreve nada no Garmin Connect. A IA usa os dados de recuperacao (sono, estresse, HRV) para de
fato ajustar a intensidade do bloco quando necessario, nao so pra comentar — isso aparece no campo
`recovery_assessment` da resposta.

## Passos

1. Rode em dry-run primeiro:
   `./.venv/Scripts/python.exe -m garmin_trainer.cli coach`
2. Mostre ao usuario a analise da IA, o que melhorou, pontos de atencao, avaliacao de recuperacao
   (sono/estresse/HRV) e a lista de treinos propostos (data, esporte, nome, descricao).
3. Pergunte explicitamente se o usuario quer publicar esses treinos no Garmin Connect antes de fazer
   qualquer envio. Publicar cria e agenda workouts na conta real do usuario — isso e uma acao que
   afeta um sistema externo, entao sempre confirme antes, mesmo que o usuario ja tenha confirmado em
   uma execucao anterior.
4. Se o usuario confirmar, rode:
   `./.venv/Scripts/python.exe -m garmin_trainer.cli coach --push`
5. Se o usuario tambem quiser o email de insights nesta execucao manual, adicione `--email`.

Use `--days-ahead N` se o usuario quiser um horizonte de planejamento diferente de 7 dias.
