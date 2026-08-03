from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from . import ai_coach, email_report, wellness, workout_builder
from .config import AppConfig, load_profile, save_profile
from .garmin_client import GarminClient
from .metrics import render_summaries_markdown, summarize_activity
from .plan_schema import CoachResponse


@dataclass
class SyncResult:
    summaries_md: str
    newest_activity_id: str | None
    new_activity_count: int


def sync_activities(client: GarminClient, profile: dict, limit: int = 10) -> SyncResult:
    last_synced = profile.get("history", {}).get("last_synced_activity_id")
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
        if sync_result.newest_activity_id:
            profile.setdefault("history", {})["last_synced_activity_id"] = sync_result.newest_activity_id
        save_profile(profile)

    if email:
        email_report.send_report(config, plan, sync_result)

    return sync_result, plan
