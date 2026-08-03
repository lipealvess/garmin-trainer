from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import yaml
from google import genai
from google.genai import types

from .config import AppConfig
from .plan_schema import CoachResponse

MODEL = "gemini-flash-latest"

SYSTEM_PROMPT = """Voce e um treinador de corrida e ciclismo experiente, especializado em \
periodizacao e prevencao de lesoes. Voce recebe o perfil do atleta, o objetivo de prova e um \
resumo das atividades recentes registradas no Garmin Connect. Sua tarefa e analisar o progresso \
e propor o proximo bloco de treinos, coerente com a fase de treinamento e a carga recente.

Regras:
- Nunca aumente volume ou intensidade em mais de ~10% em relacao a semana anterior.
- Inclua sempre aquecimento e desaquecimento nos treinos de qualidade (intervalado, tempo run).
- Respeite os dias a evitar e as preferencias informadas no perfil.
- Use como alvo zonas de FC (hr_zone 1-5) ou pace (pace_min_per_km), nunca ambos no mesmo step.
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
    athlete_context = {k: v for k, v in profile.items() if k != "history"}
    athlete_yaml = yaml.safe_dump(athlete_context, allow_unicode=True, sort_keys=False)
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
    client = genai.Client(api_key=config.gemini_api_key)
    start_date = start_date or date.today()

    response = client.models.generate_content(
        model=MODEL,
        contents=_build_user_prompt(profile, activity_summary_md, wellness_summary_md, start_date, days_ahead),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_json_schema=CoachResponse.model_json_schema(),
            temperature=0.4,
        ),
    )

    if not response.text:
        raise RuntimeError(f"Gemini nao retornou texto. Resposta bruta: {response}")

    return CoachResponse.model_validate_json(response.text)
