from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ActivitySummary(BaseModel):
    activity_id: str
    name: str
    sport: str
    date: str
    distance_km: float
    duration_min: float
    avg_hr: float | None
    max_hr: float | None
    avg_pace_min_per_km: float | None
    elevation_gain_m: float | None
    aerobic_training_effect: float | None
    anaerobic_training_effect: float | None


def _pace_min_per_km(distance_m: float, duration_s: float) -> float | None:
    if not distance_m:
        return None
    return (duration_s / 60) / (distance_m / 1000)


def summarize_activity(raw: dict[str, Any]) -> ActivitySummary:
    distance_m = raw.get("distance") or 0.0
    duration_s = raw.get("duration") or 0.0
    return ActivitySummary(
        activity_id=str(raw.get("activityId")),
        name=raw.get("activityName", "Atividade"),
        sport=(raw.get("activityType") or {}).get("typeKey", "other"),
        date=(raw.get("startTimeLocal") or "")[:10],
        distance_km=round(distance_m / 1000, 2),
        duration_min=round(duration_s / 60, 1),
        avg_hr=raw.get("averageHR"),
        max_hr=raw.get("maxHR"),
        avg_pace_min_per_km=_pace_min_per_km(distance_m, duration_s),
        elevation_gain_m=raw.get("elevationGain"),
        aerobic_training_effect=_round_or_none(raw.get("aerobicTrainingEffect")),
        anaerobic_training_effect=_round_or_none(raw.get("anaerobicTrainingEffect")),
    )


def _round_or_none(value: float | None) -> float | None:
    return round(value, 1) if value is not None else None


def render_summaries_markdown(summaries: list[ActivitySummary]) -> str:
    if not summaries:
        return "Nenhuma atividade nova desde a ultima sincronizacao."

    lines = ["| Data | Nome | Esporte | Dist (km) | Dur (min) | FC media | FC max | Pace (min/km) | TE aerobico | TE anaerobico |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for s in summaries:
        lines.append(
            f"| {s.date} | {s.name} | {s.sport} | {s.distance_km} | {s.duration_min} | "
            f"{s.avg_hr or '-'} | {s.max_hr or '-'} | "
            f"{round(s.avg_pace_min_per_km, 2) if s.avg_pace_min_per_km else '-'} | "
            f"{s.aerobic_training_effect or '-'} | {s.anaerobic_training_effect or '-'} |"
        )
    return "\n".join(lines)
