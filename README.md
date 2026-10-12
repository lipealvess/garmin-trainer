# garmin-trainer

Treinador automatizado de corrida em cima do Garmin Connect: a IA (Google Gemini) monta o plano
semanal e publica no relógio, analisa cada treino e manda um relatório matinal de saúde, tudo por
email (Gmail).

Entre 2026-09-13 e 2026-10-11 o plano foi do treinador Greg (Garmin Coach). Desde 2026-10-12 o
garmin-trainer voltou a montar os treinos.

```
Garmin Connect --(atividades, treino prescrito, sono, HRV, FC, estresse, body battery, passos)--> garmin-trainer
                                                                                                    |
                                                                       Gemini (JSON estruturado) <--+
                                                                                                    |
                                                                       email HTML (Gmail) <---------+
```

## O que você recebe

**0. O plano da semana**, todo domingo (ou no primeiro dia em que o PC ligar na semana): os treinos já
aparecem no calendário do relógio, e o email explica o porquê de cada um. Rodagens leves e longão são
guiados por **faixa de FC** (Z2 do perfil, 140–155 bpm); treinos de qualidade, por pace. Se o sono, o
HRV ou a FC de repouso indicarem fadiga, o planejador tira a intensidade da semana.

**1. Um email por atividade**, assim que ela aparece no Garmin Connect (checagem a cada 30 min):
- veredito do treino e esforço real (leve → muito forte);
- prescrito × executado (pace/FC alvo de cada bloco do treino agendado);
- FC: tempo por zona, desacoplamento pace:FC (deriva cardíaca), efeito do calor;
- ritmo volta a volta e cadência;
- o que foi bem, pontos de atenção e dicas de recuperação.

**2. Um relatório matinal por dia**, assim que o sono da noite sincroniza (ou a partir das 11h):
- prontidão do dia (alta/moderada/baixa);
- sono: duração, score, fases (profundo/REM), estresse e FC durante o sono;
- recuperação: HRV × faixa normal, FC de repouso × média de 7 dias, body battery ao acordar;
- o dia de ontem: estresse, minutos em estresse alto, passos × meta, minutos de intensidade;
- tendências de 7 dias, contagem regressiva da prova, previsão de tempo do Garmin e peso;
- o treino de hoje e como executá-lo dada a prontidão;
- dicas práticas para hoje.

## Arquitetura

| Módulo | Papel |
|---|---|
| `garmin_client.py` | wrapper da lib `garminconnect` (API não oficial) |
| `metrics.py` | resumo da atividade, voltas, desacoplamento pace:FC, treino prescrito em texto |
| `wellness.py` | métricas diárias (sono, HRV, `get_stats`, peso) |
| `ai_coach.py` | prompts (planejador, análise, relatório) + Gemini com schema JSON e fallback entre modelos |
| `workout_builder.py` | plano estruturado → treino do Garmin (alvos de pace e de faixa de bpm) |
| `plan_schema.py` | schemas das respostas da IA (`CoachResponse`, `ActivityAnalysis`, `MorningReport`, ...) |
| `email_report.py` | emails HTML (com versão texto) via SMTP |
| `pipeline.py` | orquestração (`run_tick`) |
| `state.py` | `data/state.json`: última atividade analisada, último relatório, treinos publicados |
| `cli.py` | linha de comando |

## Setup (Linux)

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env      # preencha GARMIN_EMAIL, GARMIN_PASSWORD, GEMINI_API_KEY e o SMTP
.venv/bin/python -m garmin_trainer.cli login-test
```

Edite `config/athlete_profile.yaml` com suas zonas, prova alvo e objetivos. A IA usa esse perfil
como contexto em tudo. Para o plano semanal, as chaves que mandam são `training` (`plan_owner`,
`auto_publish`, `days_per_week`, `periodization`, `key_rules`) e `preferences.preferred_training_days`.

### Email (Gmail)

No `.env`:

```
SMTP_USER=seu_email@gmail.com
SMTP_PASSWORD=<senha de app do Gmail>
EMAIL_TO=seu_email@gmail.com
```

Para gerar a senha de app: ative a verificação em duas etapas em https://myaccount.google.com/security
e crie a senha em https://myaccount.google.com/apppasswords (16 caracteres).

## Automação (systemd, Linux)

```bash
scripts/install_linux_timer.sh            # instala e ativa
scripts/install_linux_timer.sh --remove   # remove
```

Isso cria um timer do systemd do usuário (`~/.config/systemd/user/garmin-trainer.{service,timer}`):

- roda 2 min depois de ligar o PC e depois a cada 30 min;
- `Persistent=true`: se o PC estava desligado ou suspenso, roda assim que ele volta;
- *linger* ativado: roda mesmo antes de você fazer login;
- publica o plano da semana aos domingos (se `training.auto_publish: true`);
- sem atividade nova e com o relatório do dia já enviado, não chama a IA nem manda email;
- sem rede, sai em silêncio e tenta de novo na próxima execução;
- em caso de falha, manda **no máximo um** email de alerta por dia.

Acompanhar:

```bash
systemctl --user list-timers garmin-trainer.timer
journalctl --user -u garmin-trainer.service
tail -f data/logs/tick_$(date +%Y%m%d).log
```

No Windows, o equivalente é `scripts/run_pipeline.ps1` no Agendador de Tarefas.

## Uso manual

```bash
.venv/bin/python -m garmin_trainer.cli tick                # o mesmo que o timer roda
.venv/bin/python -m garmin_trainer.cli plan                # rascunho do plano da semana (não publica)
.venv/bin/python -m garmin_trainer.cli plan --push --email # publica no relógio e manda por email
.venv/bin/python -m garmin_trainer.cli daily               # força o relatório matinal agora
.venv/bin/python -m garmin_trainer.cli daily --no-email    # só no terminal, não avança o estado
.venv/bin/python -m garmin_trainer.cli review --limit 5    # análise retrospectiva das últimas corridas
.venv/bin/python -m garmin_trainer.cli sync                # só lista as atividades novas
```

Pelo Claude Code: `/garmin-coach`, `/garmin-pipeline`, `/garmin-review`, `/garmin-sync`, `/garmin-setup`.

Publicar (`--push`) apaga os treinos **futuros** do plano anterior e agenda os novos; treinos de dias
que já passaram ficam, porque a análise de cada atividade compara com o treino prescrito.

## Limitações

- **API não oficial**: a lib `garminconnect` faz engenharia reversa do Garmin Connect e pode quebrar
  se a Garmin mudar a API interna.
- **MFA**: se a conta tiver dois fatores, o primeiro login precisa ser interativo (`login-test`). Depois
  o token fica em cache em `.garminconnect_tokens/` (nunca commitar).
- **Zonas de FC**: o relógio tem as próprias zonas (usadas em "tempo por zona"), que diferem das
  `hr_zones` do perfil. A IA é instruída a deixar claro de qual está falando.
- **Gemini free tier**: devolve 503 com alguma frequência em horários de pico. Por isso há fallback
  entre modelos (`MODEL` / `FALLBACK_MODELS` em `ai_coach.py`). Se todos falharem, o email sai só
  com as métricas.
- **O PC precisa estar ligado** para os emails saírem. Atividades feitas com o PC desligado são
  analisadas na próxima vez que ele ligar (até 3 dias para trás).
