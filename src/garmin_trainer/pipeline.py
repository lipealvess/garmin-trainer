from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from . import ai_coach, email_report, wellness, workout_builder
from .config import AppConfig, load_profile, save_profile
from .garmin_client import GarminClient
from .metrics import (
    ActivityDetail,
    build_activity_detail,
    render_activity_detail_markdown,
    render_summaries_markdown,
    summarize_activity,
)
from .plan_schema import ActivityAnalysis, CoachResponse, MorningReport, TrainerReview
from .state import load_state, save_state

# Se o sono da noite ainda nao sincronizou (relogio sem contato com o celular), o relatorio
# matinal espera; a partir desta hora sai mesmo assim, com o que houver.
MORNING_FALLBACK_HOUR = 11
# Se a ultima atividade analisada nao aparece mais na lista recente (muito tempo sem rodar),
# analisa so as atividades destes ultimos dias, em vez de despejar emails de semanas atras.
ACTIVITY_LOOKBACK_DAYS = 3


@dataclass
class SyncResult:
    summaries_md: str
    newest_activity_id: str | None
    new_activity_count: int


def sync_activities(client: GarminClient, profile: dict, limit: int = 10) -> SyncResult:
    last_synced = load_state().get("last_synced_activity_id")
    raw_activities = client.recent_activities(limit=limit)

    new_raw = []
    for raw in raw_activities:
        activity_id = str(raw.get("activityId"))
        if last_synced and activity_id == str(last_synced):
            break
        new_raw.append(raw)

    summaries = [summarize_activity(raw) for raw in reversed(new_raw)]
    newest_id = str(raw_activities[0]["activityId"]) if raw_activities else None
    return SyncResult(
        summaries_md=render_summaries_markdown(summaries),
        newest_activity_id=newest_id,
        new_activity_count=len(new_raw),
    )


def generate_coach_plan(
    config: AppConfig,
    client: GarminClient,
    profile: dict,
    sync_result: SyncResult,
    days_ahead: int = 7,
    start_date: date | None = None,
    wellness_days: int = 3,
) -> CoachResponse:
    wellness_summary_md = wellness.render_wellness_markdown(
        wellness.fetch_wellness(client, days=wellness_days)
    )
    return ai_coach.generate_plan(
        config,
        profile,
        sync_result.summaries_md,
        wellness_summary_md,
        days_ahead=days_ahead,
        start_date=start_date,
    )


def push_plan(client: GarminClient, profile: dict, plan: CoachResponse) -> list[dict]:
    """Publica o plano no Garmin, substituindo os treinos futuros do ciclo anterior.

    Sem isso, cada execucao do pipeline empilharia treinos novos em cima dos ja agendados
    (workouts nao completados nao desaparecem sozinhos do calendario).
    """
    previous_ids = profile.get("history", {}).get("last_pushed_workout_ids", [])
    for workout_id in previous_ids:
        try:
            client.api.delete_workout(workout_id)
        except Exception:
            pass  # ja completado, ja removido manualmente, ou expirado — segue o baile

    uploaded = []
    for planned_workout in plan.planned_workouts:
        workout = workout_builder.build_workout(planned_workout)
        result = client.upload_and_schedule(workout, planned_workout.sport, planned_workout.date)
        uploaded.append(result)

    new_ids = [
        str(u.get("workoutId") or u.get("workoutSummary", {}).get("workoutId")) for u in uploaded
    ]
    profile.setdefault("history", {})["last_pushed_workout_ids"] = new_ids
    return uploaded


def run_pipeline(
    config: AppConfig,
    push: bool = False,
    days_ahead: int = 7,
    start_date: date | None = None,
    email: bool = False,
) -> tuple[SyncResult, CoachResponse | None]:
    profile = load_profile()
    client = GarminClient(config)
    client.login()

    sync_result = sync_activities(client, profile)

    if push and sync_result.new_activity_count == 0:
        return sync_result, None

    plan = generate_coach_plan(config, client, profile, sync_result, days_ahead=days_ahead, start_date=start_date)

    if push:
        push_plan(client, profile, plan)
        save_profile(profile)
        if sync_result.newest_activity_id:
            state = load_state()
            state["last_synced_activity_id"] = sync_result.newest_activity_id
            save_state(state)

    if email:
        email_report.send_report(config, plan, sync_result)

    return sync_result, plan


@dataclass
class ActivityResult:
    detail: ActivityDetail
    analysis: ActivityAnalysis | None
    error: str | None


@dataclass
class TickResult:
    activities: list[ActivityResult] = field(default_factory=list)
    morning: MorningReport | None = None
    morning_sent: bool = False
    morning_error: str | None = None
    morning_skipped_reason: str | None = None


def _find_new_activities(
    raw_activities: list[dict[str, Any]], last_synced: str | None
) -> list[dict[str, Any]]:
    """Atividades mais novas que a ultima analisada, da mais antiga para a mais nova."""
    new = []
    for raw in raw_activities:
        if last_synced and str(raw.get("activityId")) == str(last_synced):
            return list(reversed(new))
        new.append(raw)
    cutoff = (date.today() - timedelta(days=ACTIVITY_LOOKBACK_DAYS)).isoformat()
    return [r for r in reversed(new) if (r.get("startTimeLocal") or "")[:10] >= cutoff]


def _fetch_activity_detail(client: GarminClient, raw: dict[str, Any]) -> ActivityDetail:
    activity_id = str(raw["activityId"])
    try:
        splits = client.activity_splits(activity_id)
    except Exception:
        splits = None
    planned = None
    if raw.get("workoutId"):
        try:
            planned = client.workout(str(raw["workoutId"]))
        except Exception:
            planned = None
    return build_activity_detail(raw, splits, planned)


def process_new_activities(
    config: AppConfig,
    client: GarminClient,
    profile: dict,
    state: dict,
    raw_activities: list[dict[str, Any]],
    email: bool,
) -> list[ActivityResult]:
    """Analisa e envia por email cada atividade nova. O estado avanca atividade a atividade, entao
    uma falha no meio (ex: SMTP fora) faz so as restantes serem retentadas na proxima execucao."""
    new = _find_new_activities(raw_activities, state.get("last_synced_activity_id"))
    if not new:
        return []

    wellness_md = wellness.render_wellness_markdown(wellness.fetch_wellness(client, days=4))
    results = []
    for raw in new:
        detail = _fetch_activity_detail(client, raw)
        history = [summarize_activity(r) for r in raw_activities if r is not raw]
        history.sort(key=lambda a: a.date)

        analysis, error = None, None
        try:
            analysis = ai_coach.generate_activity_analysis(
                config, profile, render_activity_detail_markdown(detail),
                render_summaries_markdown(history), wellness_md,
            )
        except Exception as exc:
            error = str(exc)

        if email:
            email_report.send_activity_report(config, detail, analysis, error)
            state["last_synced_activity_id"] = detail.summary.activity_id
            save_state(state)
        results.append(ActivityResult(detail, analysis, error))
    return results


def _fmt_seconds(seconds: float | None) -> str:
    if not seconds:
        return "-"
    seconds = int(seconds)
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def _race_context_md(client: GarminClient, profile: dict) -> str:
    lines = []
    primary = (profile.get("goal") or {}).get("primary") or {}
    if primary.get("race_date"):
        days_left = (date.fromisoformat(str(primary["race_date"])) - date.today()).days
        lines.append(
            f"- Prova alvo: {primary.get('race_name')} em {primary['race_date']} ({days_left} dias), "
            f"meta {primary.get('target_time') or '-'}"
        )
    try:
        pred = client.race_predictions() or {}
        lines.append(
            f"- Previsao do Garmin: 5K {_fmt_seconds(pred.get('time5K'))}, 10K {_fmt_seconds(pred.get('time10K'))}, "
            f"meia {_fmt_seconds(pred.get('timeHalfMarathon'))}"
        )
    except Exception:
        pass
    return "\n".join(lines) or "Sem prova alvo definida."


def run_morning_report(
    config: AppConfig,
    client: GarminClient,
    profile: dict,
    state: dict,
    raw_activities: list[dict[str, Any]],
    email: bool,
) -> tuple[MorningReport | None, str | None]:
    days = wellness.fetch_wellness(client, days=7)
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    recent = sorted(
        (summarize_activity(r) for r in raw_activities if (r.get("startTimeLocal") or "")[:10] >= cutoff),
        key=lambda a: a.date,
    )

    report, error = None, None
    try:
        report = ai_coach.generate_morning_report(
            config, profile, wellness.render_wellness_markdown(days),
            render_summaries_markdown(recent), _race_context_md(client, profile),
        )
    except Exception as exc:
        error = str(exc)

    # Sem email (teste manual) o estado nao avanca, para nao "consumir" o envio real.
    if email:
        email_report.send_morning_report(config, days, report, error)
        state["last_morning_report_date"] = date.today().isoformat()
        save_state(state)
    return report, error


def run_tick(config: AppConfig, email: bool = True, force_morning: bool = False) -> TickResult:
    """Execucao agendada (a cada 30 min e ao ligar o PC). So acompanha - nunca gera nem publica
    treinos, quem monta o plano e o treinador Greg (Garmin Coach).

    1. Cada atividade nova -> email com a analise do treino.
    2. Uma vez por dia -> relatorio matinal (sono, HRV, FC, estresse, body battery, passos), assim
       que o sono da noite tiver sincronizado (ou a partir de MORNING_FALLBACK_HOUR).
    Sem novidade, nao chama a IA nem manda email.
    """
    profile = load_profile()
    state = load_state()
    client = GarminClient(config)
    client.login()

    raw_activities = client.recent_activities(limit=15)
    result = TickResult()
    result.activities = process_new_activities(config, client, profile, state, raw_activities, email)

    today = date.today().isoformat()
    if not force_morning and state.get("last_morning_report_date") == today:
        result.morning_skipped_reason = "relatorio de hoje ja enviado"
    elif (
        not force_morning
        and datetime.now().hour < MORNING_FALLBACK_HOUR
        and not wellness.has_sleep_data(client, today)
    ):
        result.morning_skipped_reason = "sono da noite ainda nao sincronizado"
    else:
        result.morning, result.morning_error = run_morning_report(
            config, client, profile, state, raw_activities, email
        )
        result.morning_sent = email
    return result


def run_trainer_review(config: AppConfig, limit: int = 5, email: bool = False) -> TrainerReview:
    """Analise retrospectiva das ultimas N atividades, sob demanda. Nunca propoe treinos."""
    profile = load_profile()
    client = GarminClient(config)
    client.login()

    raw_activities = client.recent_activities(limit=limit, activity_type="running")
    summaries = [summarize_activity(r) for r in raw_activities]
    summaries.sort(key=lambda s: s.date)
    activity_summary_md = render_summaries_markdown(summaries)

    wellness_days = wellness.fetch_wellness(client, days=limit)
    wellness_summary_md = wellness.render_wellness_markdown(wellness_days)

    review = ai_coach.generate_trainer_review(config, profile, activity_summary_md, wellness_summary_md)

    if email:
        email_report.send_review_report(config, review, activity_summary_md)

    return review
