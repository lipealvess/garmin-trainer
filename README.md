# garmin-trainer

Pipeline automatizado: a IA (Google Gemini) analisa suas atividades, sono, estresse e HRV do Garmin
Connect e gera o proximo bloco de treinos, que e publicado e agendado de volta no seu relogio Garmin.

```
Garmin Connect  --(atividades + sono/estresse/HRV)-->  garmin-trainer
                                                              |
                                                              v
                                                   resumo compacto (markdown)
                                                              |
                                                              v
                                                   Gemini API (JSON schema estruturado)
                                                              |
                                                              v
                                                plano de treino + insights (JSON tipado)
                                                              |
                                                              v
                                          workout builder (garminconnect.workout)
                                                              |
                                                              v
Garmin Connect  <--(upload + schedule_workout)--  garmin-trainer  --(email)--> caixa de entrada
```

## Como funciona

1. **Sync**: busca no Garmin Connect as atividades novas desde a ultima sincronizacao
   (`garmin_client.py`, `metrics.py`), alem de sono, estresse, HRV e FC de repouso dos ultimos dias
   (`wellness.py`).
2. **Coach**: monta um prompt com o perfil do atleta (`config/athlete_profile.yaml`), o resumo das
   atividades e os dados de recuperacao, e chama a API do Google Gemini (tier gratuito) forcando uma
   resposta estruturada via JSON schema (`ai_coach.py`, `plan_schema.py`). A IA usa sono/estresse/HRV
   para de fato ajustar a intensidade do bloco (nao so comentar), e explica isso em
   `recovery_assessment`.
3. **Build + push**: converte o plano estruturado em objetos `RunningWorkout`/`CyclingWorkout` da
   biblioteca `garminconnect` e publica + agenda no Garmin Connect (`workout_builder.py`,
   `garmin_client.py`).
4. **Email**: opcionalmente envia um relatorio por email com os insights (`email_report.py`).

Tudo isso e orquestrado em `pipeline.py` e exposto via CLI em `cli.py`.

## Setup

```
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e .
copy .env.example .env   # preencha GARMIN_EMAIL, GARMIN_PASSWORD, GEMINI_API_KEY
```

Edite `config/athlete_profile.yaml` com suas zonas de FC reais, objetivo de prova e preferencias.

Teste o login:

```
./.venv/Scripts/python.exe -m garmin_trainer.cli login-test
```

Ou peça para o Claude Code rodar a skill `/garmin-setup`, que guia esse processo.

## Uso

```
# so ler as atividades novas, sem chamar a IA
./.venv/Scripts/python.exe -m garmin_trainer.cli sync

# gerar o proximo bloco de treinos (dry-run, nao publica nada)
./.venv/Scripts/python.exe -m garmin_trainer.cli coach

# gerar e publicar/agendar no Garmin Connect
./.venv/Scripts/python.exe -m garmin_trainer.cli coach --push

# pipeline completo: sync + coach + push
./.venv/Scripts/python.exe -m garmin_trainer.cli run --push
```

Ou via Claude Code, usando as skills do projeto: `/garmin-sync`, `/garmin-coach`, `/garmin-pipeline`.

## Automacao (Agendador de Tarefas do Windows)

O pipeline roda sozinho, sem depender de sessao do Claude Code nem de nuvem — via **Agendador de
Tarefas do Windows**, executando `scripts/run_pipeline.ps1` localmente (usa o `.venv` e o `.env` do
projeto).

- Tarefa: `GarminTrainerPipeline` (ver no Agendador de Tarefas do Windows).
- Frequencia: a cada 2 dias, 06:00, comecando em 2026-07-25.
- "Executar assim que possivel apos inicializacao perdida" ativado — se o notebook estiver desligado
  no horario, roda assim que for ligado.
- Publica automaticamente no Garmin (`--push`), sem pedir confirmacao — autorizado pelo usuario em
  2026-07-24 apos validar o fluxo completo contra a conta real.
- **So gera/publica plano novo se houver atividade nova desde a ultima execucao** — evita chamadas
  desnecessarias a IA e evita duplicar treinos no calendario.
- **Substitui os treinos futuros do ciclo anterior** antes de publicar os novos (nao empilha).
- Envia um **email de insights** (`--email`) a cada execucao com plano novo: o que melhorou, pontos
  de atencao e metricas/alvos para os proximos treinos.
- Logs em `data/logs/pipeline_<timestamp>.log`, plano gerado em `data/plans/plan_<timestamp>.json`.

### Configurar o email de insights

Preencha no `.env` (veja `.env.example`):

```
SMTP_USER=seu_email@gmail.com
SMTP_PASSWORD=<senha de app do Gmail>
EMAIL_TO=seu_email@gmail.com
```

Pra gerar a senha de app do Gmail (gratis, nao e a senha normal da conta):
1. Ative a **Verificacao em duas etapas** em https://myaccount.google.com/security (se ainda nao tiver).
2. Va em https://myaccount.google.com/apppasswords, crie uma senha de app (ex: nome "garmin-trainer").
3. Cole o codigo de 16 caracteres gerado em `SMTP_PASSWORD` no `.env`.

Teste isolado sem publicar nada no Garmin: `garmin-trainer coach --email` (dry-run + email).

Para reconfigurar (horario, frequencia): PowerShell -> `Set-ScheduledTask` / recriar via
`Register-ScheduledTask`, ou pelo painel grafico "Agendador de Tarefas" do Windows.

## Limitacoes e pontos a validar

- **API nao oficial**: usa a biblioteca `garminconnect` (engenharia reversa do Garmin Connect, sem
  suporte oficial da Garmin). Pode quebrar se a Garmin mudar a API interna.
- **Alvos de treino (FC/pace) sao best-effort**: os campos `targetValueOne`, `targetValueTwo` e
  `zoneNumber` enviados nos steps de treino foram inferidos a partir do schema Pydantic da lib
  (`garminconnect.workout`, que aceita campos extras) e de convencoes observadas no codigo-fonte, mas
  **nao foram validados contra uma conta Garmin real**. Antes de confiar no fluxo 100% automatico,
  publique um treino de teste com `coach --push` e confira no app Garmin Connect / no relogio se os
  alvos de FC e pace aparecem corretos.
- **MFA**: se sua conta Garmin tiver autenticacao de dois fatores, o CLI vai pedir o codigo
  interativamente no terminal — nao funciona sem interacao na primeira vez (o token fica em cache
  depois, em `.garminconnect_tokens/`, que nunca deve ser commitado).
- **Nomes de campos das atividades** (`activityId`, `averageHR`, etc., em `metrics.py`) seguem a
  convencao conhecida do Garmin Connect, mas vale conferir com `sync` numa conta real antes de
  confiar cegamente nos numeros.
- **Gemini free tier**: a chave em `GEMINI_API_KEY` e gerada em https://aistudio.google.com (API key,
  gratis, sem cartao). O tier gratuito do modelo `gemini-2.5-flash` tem limite de requisicoes por
  minuto/dia (na ordem de dezenas por minuto, ~1000/dia) — mais do que suficiente para rodar o `coach`
  algumas vezes por semana, mas nao adequado para chamar em loop apertado.
