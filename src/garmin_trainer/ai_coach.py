from __future__ import annotations

from datetime import date
from typing import Any, TypeVar

import yaml
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

from .config import AppConfig
from .plan_schema import ActivityAnalysis, CoachResponse, MorningReport, TrainerReview
from .retry import call_with_retry

MODEL = "gemini-flash-latest"
# O free tier devolve 503 ("high demand") com frequencia; cai para outros modelos antes de desistir.
FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-flash-lite-latest"]

T = TypeVar("T", bound=BaseModel)


def _generate(config: AppConfig, schema: type[T], system_prompt: str, user_prompt: str, temperature: float) -> T:
    client = genai.Client(api_key=config.gemini_api_key)
    generate_config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        response_json_schema=schema.model_json_schema(),
        temperature=temperature,
    )
    last_error: Exception | None = None
    for model in [MODEL, *FALLBACK_MODELS]:
        try:
            response = call_with_retry(
                lambda: client.models.generate_content(model=model, contents=user_prompt, config=generate_config),
                attempts=2,
            )
        except genai_errors.APIError as exc:
            last_error = exc
            continue
        if not response.text:
            raise RuntimeError(f"Gemini nao retornou texto. Resposta bruta: {response}")
        return schema.model_validate_json(response.text)
    raise RuntimeError(f"Todos os modelos Gemini falharam. Ultimo erro: {last_error}")


def _athlete_yaml(profile: dict[str, Any]) -> str:
    athlete_context = {k: v for k, v in profile.items() if k != "history"}
    return yaml.safe_dump(athlete_context, allow_unicode=True, sort_keys=False)

_MONITOR_ROLE = """Voce e o personal trainer de Filipe, um corredor. Desde 2026-10-12 o plano de treinos \
dele e montado pelo proprio garmin-trainer (o planejador semanal, que e voce em outro momento). Nesta \
tarefa voce NAO muda o plano: voce monitora, interpreta os dados do relogio e explica ao atleta o que \
eles mostram. Ajustes de plano acontecem no planejamento semanal, que le estes mesmos dados.

Regras gerais:
- Nao proponha series/volumes novos aqui. Pode dizer o que os dados sugerem para os proximos dias
  (ex: "com esse HRV, faca o treino de amanha no limite inferior da faixa de FC").
- Existem dois conjuntos de zonas de FC: as do perfil (hr_zones, calibradas pela FC maxima observada) e
  as configuradas no relogio (usadas no "tempo por zona"). Deixe claro de qual voce esta falando.
- Paces estao no formato min:seg por km.
- Seja direto e especifico, cite numeros reais. Escreva em portugues do Brasil com acentuacao correta, em tom pessoal
  ("voce"), com frases curtas. Cada campo cobre um angulo diferente - nao repita informacao.
- Responda exclusivamente em JSON valido seguindo o schema fornecido, sem texto fora do JSON.
"""

ACTIVITY_SYSTEM_PROMPT = _MONITOR_ROLE + """
Tarefa: analisar UMA atividade que acabou de ser registrada. Compare a execucao com o treino prescrito
(quando houver) bloco a bloco, analise FC (zonas, desacoplamento pace:FC - abaixo de 5% e bom,
acima de 10% e deriva forte), distribuicao de ritmo nas voltas, cadencia, e o efeito do calor quando a
temperatura passar de ~26 C. Em treinos leves guiados por FC, o sucesso e ficar na faixa de FC, nao o
pace - elogie quando ele desacelerou para respeitar a FC. Use o contexto de sono/HRV dos ultimos dias
para explicar a resposta do corpo, e o historico recente para dizer se houve evolucao.
"""

MORNING_SYSTEM_PROMPT = _MONITOR_ROLE + """
Tarefa: relatorio matinal de saude e prontidao. Voce recebe 7 dias de metricas (sono, fases do sono,
HRV, FC de repouso, body battery, estresse, passos, minutos de intensidade, peso), as atividades
recentes e o treino planejado para hoje (se houver). Sono/HRV de hoje sao da noite passada; as metricas
de "dia" de hoje sao parciais - para falar do dia, use o de ontem. Compare sempre com a media dos
ultimos dias e com a faixa normal (baseline) do proprio atleta, nao com numeros genericos. Se houver
treino hoje, diga em tips_for_today como executa-lo dada a prontidao (ex: manter o limite inferior da
faixa de FC, ou trocar por descanso se a prontidao estiver baixa e o treino for de qualidade).
"""

REVIEW_SYSTEM_PROMPT = """Voce e o personal trainer de Filipe, um corredor. Voce foi chamado para fazer \
uma analise retrospectiva das atividades recentes dele, olhando pace, FC, aderencia as zonas do perfil \
(hr_zones/pace_zones), deriva cardiaca, consistencia e evolucao ao longo do periodo, alem dos dados de \
sono/estresse/HRV/peso disponiveis.

Regras:
- Esta e uma analise, nao um plano: nao monte series ou semanas de treino aqui.
- Seja especifico: cite paces, FC media/maxima e datas reais das atividades analisadas.
- Se houver sinais de deriva cardiaca ou de esforco desalinhado com o proposito do treino, aponte isso
  claramente como ponto de atencao.
- Se peso corporal estiver disponivel e o atleta tiver objetivo de perda de peso, comente a tendencia.
- Responda exclusivamente em JSON valido seguindo o schema fornecido, sem texto fora do JSON.
"""

SYSTEM_PROMPT = """Voce e o treinador de corrida de Filipe, experiente em periodizacao e prevencao de \
lesoes. Voce monta o plano semanal dele, que e publicado automaticamente no relogio Garmin. Voce recebe o \
perfil (objetivo, fase da periodizacao, regras em training.key_rules), as atividades das ultimas semanas, \
7 dias de metricas de recuperacao e o plano da semana anterior.

Regras de planejamento:
- Siga training.days_per_week e preferences.preferred_training_days. Em dias sem corrida nao gere treino.
- Respeite a fase atual de training.periodization e training.key_rules - elas foram escritas a partir do
  historico real do atleta e tem prioridade sobre convencoes genericas.
- Nunca aumente o volume semanal em mais de ~10% em relacao a semana anterior realmente executada.
- Rodagens leves e longao: alvo por FC com kind="hr_range" usando a faixa Z2 do perfil (hr_zones.z2,
  ex: hr_min_bpm=140, hr_max_bpm=155), duracao por TEMPO. O pace vai sair mais lento que o habitual
  (8:00-9:00/km) e isso e o objetivo. Na description, diga explicitamente para caminhar se a FC passar
  do limite e que o pace nao importa nesses treinos.
- Treinos de qualidade: alvo por pace (kind="pace") usando as pace_zones do perfil (min = mais rapido,
  max = mais lento). pace_min_per_km = centro da faixa e pace_tolerance_min_per_km cobrindo a faixa.
  Sempre com aquecimento e desaquecimento leves (hr_range Z1/Z2). Use blocos de repeticao
  (repeat_iterations + repeat_steps) para intervalados.
- Nunca use kind="hr_zone" (as zonas do relogio sao diferentes das do perfil).
- Use os dados de recuperacao para decidir de verdade:
  - Sono ruim (score < ~60 ou < 6h) em mais de uma das ultimas noites, HRV abaixo da faixa normal
    (baseline) ou status LOW/UNBALANCED, ou FC de repouso 4+ bpm acima da media de 7 dias: sem
    qualidade no inicio da semana; troque por leve ou reduza.
  - Estresse medio diario consistentemente alto (> ~50): trate como carga adicional.
- Cada treino precisa de nome curto e claro (ex: "Rodagem leve por FC 35 min") e description com o
  proposito e como executar (em portugues, 2-4 frases).
- Campos do relatorio (vao por email): week_focus (1 frase), analysis (racional da semana: por que esses
  treinos, como encaixam na fase), highlights (o que melhorou nas ultimas semanas), improvement_areas,
  next_targets (o que observar nesta semana: faixas de FC, paces, volume total) e recovery_assessment
  (como a recuperacao atual mudou o plano). Tom direto e pessoal, com numeros reais.
- Responda exclusivamente em JSON valido seguindo o schema fornecido, sem texto fora do JSON.
"""


def _build_user_prompt(
    profile: dict[str, Any],
    activity_summary_md: str,
    wellness_summary_md: str,
    start_date: date,
    end_date: date,
    previous_plan_md: str,
) -> str:
    return f"""## Perfil do atleta
{_athlete_yaml(profile)}

## Janela de planejamento
De {start_date.isoformat()} ({_WEEKDAYS[start_date.weekday()]}) ate {end_date.isoformat()} \
({_WEEKDAYS[end_date.weekday()]}), inclusive. Nao gere treinos fora dessa janela.

## Plano da semana anterior
{previous_plan_md}

## Atividades das ultimas 4 semanas
{activity_summary_md}

## Recuperacao dos ultimos 7 dias
{wellness_summary_md}

Gere o plano da semana."""


def generate_plan(
    config: AppConfig,
    profile: dict[str, Any],
    activity_summary_md: str,
    wellness_summary_md: str,
    start_date: date,
    end_date: date,
    previous_plan_md: str = "Nenhum plano anterior do garmin-trainer.",
) -> CoachResponse:
    return _generate(
        config,
        CoachResponse,
        SYSTEM_PROMPT,
        _build_user_prompt(profile, activity_summary_md, wellness_summary_md, start_date, end_date, previous_plan_md),
        temperature=0.4,
    )


def generate_activity_analysis(
    config: AppConfig,
    profile: dict[str, Any],
    activity_detail_md: str,
    recent_activities_md: str,
    wellness_summary_md: str,
) -> ActivityAnalysis:
    prompt = f"""## Perfil do atleta
{_athlete_yaml(profile)}

## Atividade a analisar
{activity_detail_md}

## Atividades anteriores (historico recente, para comparar)
{recent_activities_md}

## Sono, HRV e recuperacao dos ultimos dias
{wellness_summary_md}

Analise essa atividade."""
    return _generate(config, ActivityAnalysis, ACTIVITY_SYSTEM_PROMPT, prompt, temperature=0.3)


def generate_morning_report(
    config: AppConfig,
    profile: dict[str, Any],
    wellness_summary_md: str,
    recent_activities_md: str,
    race_context_md: str,
    planned_today_md: str = "Nenhum treino planejado para hoje.",
) -> MorningReport:
    prompt = f"""## Hoje
{date.today().isoformat()} ({_WEEKDAYS[date.today().weekday()]})

## Perfil do atleta
{_athlete_yaml(profile)}

## Metricas dos ultimos 7 dias
{wellness_summary_md}

## Atividades dos ultimos 7 dias
{recent_activities_md}

## Prova alvo e previsoes do Garmin
{race_context_md}

## Treino planejado para hoje
{planned_today_md}

Gere o relatorio matinal."""
    return _generate(config, MorningReport, MORNING_SYSTEM_PROMPT, prompt, temperature=0.3)


_WEEKDAYS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]


def _build_review_prompt(profile: dict[str, Any], activity_summary_md: str, wellness_summary_md: str) -> str:
    athlete_yaml = _athlete_yaml(profile)
    return f"""## Perfil do atleta
{athlete_yaml}

## Atividades recentes analisadas
{activity_summary_md}

## Sono, estresse, HRV e peso do periodo
{wellness_summary_md}

Faca a analise retrospectiva dessas atividades: o que evoluiu, pontos de atencao, e leitura da
recuperacao/peso no periodo."""


def generate_trainer_review(
    config: AppConfig,
    profile: dict[str, Any],
    activity_summary_md: str,
    wellness_summary_md: str,
) -> TrainerReview:
    return _generate(
        config,
        TrainerReview,
        REVIEW_SYSTEM_PROMPT,
        _build_review_prompt(profile, activity_summary_md, wellness_summary_md),
        temperature=0.4,
    )
