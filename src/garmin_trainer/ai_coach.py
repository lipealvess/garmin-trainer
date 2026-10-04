from __future__ import annotations

from datetime import date, timedelta
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

_MONITOR_ROLE = """Voce e o personal trainer de acompanhamento de Filipe, um corredor. IMPORTANTE: \
voce NAO prescreve treinos - o treinador Greg (via Garmin Coach) ja monta o plano de treinos dele. Seu \
papel e monitorar, interpretar os dados do relogio e explicar ao atleta o que eles mostram.

Regras gerais:
- Nunca proponha treinos, series, volumes ou paces-alvo futuros - isso e trabalho do Greg. Voce pode
  apontar o que os dados sugerem (ex: "a FC mostra que esse pace ainda e forte pra voce") e sugerir
  que ele converse com o Greg / ajuste no app se algo estiver desalinhado.
- Existem dois conjuntos de zonas de FC: as do perfil (hr_zones, calibradas pela FC maxima observada) e
  as configuradas no relogio (usadas no "tempo por zona"). Deixe claro de qual voce esta falando.
- Paces estao no formato min:seg por km.
- Seja direto e especifico, cite numeros reais. Escreva em portugues do Brasil com acentuacao correta, em tom pessoal
  ("voce"), com frases curtas. Cada campo cobre um angulo diferente - nao repita informacao.
- Responda exclusivamente em JSON valido seguindo o schema fornecido, sem texto fora do JSON.
"""

ACTIVITY_SYSTEM_PROMPT = _MONITOR_ROLE + """
Tarefa: analisar UMA atividade que acabou de ser registrada. Compare a execucao com o treino prescrito
pelo Greg (quando houver) bloco a bloco, analise FC (zonas, desacoplamento pace:FC - abaixo de 5% e bom,
acima de 10% e deriva forte), distribuicao de ritmo nas voltas, cadencia, e o efeito do calor quando a
temperatura passar de ~26 C. Use o contexto de sono/HRV dos ultimos dias para explicar a resposta do
corpo, e o historico recente para dizer se houve evolucao.
"""

MORNING_SYSTEM_PROMPT = _MONITOR_ROLE + """
Tarefa: relatorio matinal de saude e prontidao. Voce recebe 7 dias de metricas (sono, fases do sono,
HRV, FC de repouso, body battery, estresse, passos, minutos de intensidade, peso) e as atividades
recentes. Sono/HRV de hoje sao da noite passada; as metricas de "dia" de hoje sao parciais - para
falar do dia, use o de ontem. Compare sempre com a media dos ultimos dias e com a faixa normal
(baseline) do proprio atleta, nao com numeros genericos. Se a prova alvo estiver proxima, considere
isso na leitura (ex: semana de polimento).
"""

REVIEW_SYSTEM_PROMPT = """Voce e o personal trainer de acompanhamento de Filipe, um corredor. IMPORTANTE: \
voce NAO prescreve treinos - o treinador Greg (via Garmin Coach) ja monta o plano de treinos dele. Voce \
foi chamado para fazer uma analise retrospectiva das atividades recentes dele, olhando pace, FC, aderencia \
as zonas do perfil (hr_zones/pace_zones), deriva cardiaca, consistencia e evolucao ao longo do periodo, \
alem dos dados de sono/estresse/HRV/peso disponiveis.

Regras:
- Nunca proponha treinos, series, paces-alvo para o futuro ou ajustes de plano - isso e trabalho do Greg.
- Seja especifico: cite paces, FC media/maxima e datas reais das atividades analisadas.
- Se houver sinais de deriva cardiaca ou de esforco desalinhado com o proposito do treino, aponte isso
  claramente como ponto de atencao.
- Se peso corporal estiver disponivel e o atleta tiver objetivo de perda de peso, comente a tendencia.
- Responda exclusivamente em JSON valido seguindo o schema fornecido, sem texto fora do JSON.
"""

SYSTEM_PROMPT = """Voce e um treinador de corrida e ciclismo experiente, especializado em \
periodizacao e prevencao de lesoes. Voce recebe o perfil do atleta, o objetivo de prova e um \
resumo das atividades recentes registradas no Garmin Connect. Sua tarefa e analisar o progresso \
e propor o proximo bloco de treinos, coerente com a fase de treinamento e a carga recente.

Regras:
- Nunca aumente volume ou intensidade em mais de ~10% em relacao a semana anterior.
- Inclua sempre aquecimento e desaquecimento nos treinos de qualidade (intervalado, tempo run).
- Respeite os dias a evitar e as preferencias informadas no perfil.
- Use pace (pace_min_per_km) como alvo primario dos steps, com base nas pace_zones do
  perfil (min = pace mais rapido, max = mais lento, dentro da zona). Defina
  pace_min_per_km como o centro da faixa da zona escolhida e pace_tolerance_min_per_km
  cobrindo essa faixa (ex: zona 7.5-8.75 -> pace_min_per_km=8.1, tolerance=~0.6). Use
  hr_zone (1-5) apenas se as pace_zones nao existirem ou nao cobrirem o esforco
  desejado. Nunca combine hr_zone e pace no mesmo step.
- Mesmo usando pace como alvo, o atleta tem historico de deriva cardiaca (FC sobe alem
  da zona esperada mesmo no pace certo). Sempre inclua na description do treino uma
  instrucao explicita de que, se a FC subir e permanecer significativamente acima da
  zona equivalente de FC (ex: acima de Z3 em treino leve), o atleta deve desacelerar
  mesmo estando dentro do pace-alvo.
- Voce tambem recebe dados de sono, estresse e HRV (variabilidade da frequencia cardiaca) dos
  ultimos dias, coletados pelo relogio. Use isso de verdade para decidir a intensidade do bloco, nao
  so para comentar:
  - Sono ruim (score abaixo de ~60, ou poucas horas) em mais de um dos ultimos dias: reduza
    intensidade do proximo treino de qualidade, ou troque por rodagem leve/descanso extra.
  - HRV status "LOW" ou "UNBALANCED": sinal de fadiga acumulada — priorize recuperacao antes de
    treino intervalado ou tempo run, mesmo que isso signifique reordenar o bloco planejado.
  - Estresse medio diario consistentemente alto (acima de ~50): trate como carga adicional ao
    volume de treino, nao ignore.
  - Se os dados de recuperacao estiverem bons/normais, siga a progressao padrao normalmente.
- Alem do plano de treinos, voce escreve um relatorio de insights (highlights, improvement_areas,
  next_targets, recovery_assessment) que vai direto por email pro atleta. Escreva em tom direto e
  pessoal, como se estivesse falando com o atleta, com frases completas e especificas (cite numeros
  reais das atividades e da recuperacao quando possivel: FC media, pace, distancia, score de sono,
  status de HRV). Nao repita o texto de analysis nesses campos — cada campo cobre um angulo
  diferente. Em recovery_assessment, seja explicito se e como a recuperacao mudou o plano gerado
  (ex: "troquei o intervalado de terca por rodagem leve porque seu HRV caiu e o sono ficou abaixo de
  6h duas noites seguidas").
- Responda exclusivamente em JSON valido seguindo o schema fornecido, sem texto fora do JSON.
"""


def _build_user_prompt(
    profile: dict[str, Any],
    activity_summary_md: str,
    wellness_summary_md: str,
    start_date: date,
    days_ahead: int,
) -> str:
    athlete_yaml = _athlete_yaml(profile)
    horizon = start_date + timedelta(days=days_ahead)
    return f"""## Perfil do atleta
{athlete_yaml}

## Janela de planejamento
De {start_date.isoformat()} ate {horizon.isoformat()} ({days_ahead} dias). Nao gere treinos com data
anterior a {start_date.isoformat()}.

## Atividades recentes (desde a ultima sincronizacao)
{activity_summary_md}

## Sono, estresse e HRV dos ultimos dias
{wellness_summary_md}

Analise o progresso recente e os sinais de recuperacao, e gere o proximo bloco de treinos dentro da
janela de planejamento."""


def generate_plan(
    config: AppConfig,
    profile: dict[str, Any],
    activity_summary_md: str,
    wellness_summary_md: str = "Sem dados de recuperacao disponiveis.",
    days_ahead: int = 7,
    start_date: date | None = None,
) -> CoachResponse:
    start_date = start_date or date.today()
    return _generate(
        config,
        CoachResponse,
        SYSTEM_PROMPT,
        _build_user_prompt(profile, activity_summary_md, wellness_summary_md, start_date, days_ahead),
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
