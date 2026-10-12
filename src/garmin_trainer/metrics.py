from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ActivitySummary(BaseModel):
    activity_id: str
    name: str
    sport: str
    date: str
    start_time: str | None = None
    distance_km: float
    duration_min: float
    avg_hr: float | None
    max_hr: float | None
    avg_pace_min_per_km: float | None
    elevation_gain_m: float | None
    aerobic_training_effect: float | None
    anaerobic_training_effect: float | None
    training_effect_label: str | None = None
    avg_cadence: float | None = None
    avg_temperature_c: float | None = None
    calories: float | None = None
    vo2max: float | None = None
    # Segundos em cada zona de FC, segundo as zonas configuradas no relogio (1..5)
    hr_time_in_zones_s: list[float] | None = None
    workout_id: str | None = None


class Lap(BaseModel):
    index: int
    kind: str | None
    distance_km: float
    duration_min: float
    pace_min_per_km: float | None
    avg_hr: float | None
    max_hr: float | None
    cadence: float | None


class ActivityDetail(BaseModel):
    summary: ActivitySummary
    laps: list[Lap] = []
    # Desacoplamento pace:FC entre 1a e 2a metade da parte principal (sem aquecimento/desaquecimento).
    # Acima de ~5% indica deriva cardiaca relevante.
    decoupling_percent: float | None = None
    planned_workout_md: str | None = None


def fmt_pace(min_per_km: float | None) -> str:
    """6.97 -> '6:58'. Decimais de minuto confundem leitura (e a IA)."""
    if not min_per_km:
        return "-"
    total = round(min_per_km * 60)
    return f"{total // 60}:{total % 60:02d}"


def _pace_from_speed(speed_m_s: float | None) -> float | None:
    return (1000 / speed_m_s) / 60 if speed_m_s else None


def _pace_min_per_km(distance_m: float, duration_s: float) -> float | None:
    if not distance_m:
        return None
    return (duration_s / 60) / (distance_m / 1000)


def _round_or_none(value: float | None, digits: int = 1) -> float | None:
    return round(value, digits) if value is not None else None


def _int_or_none(value: float | None) -> int | None:
    return round(value) if value is not None else None


def summarize_activity(raw: dict[str, Any]) -> ActivitySummary:
    distance_m = raw.get("distance") or 0.0
    duration_s = raw.get("duration") or 0.0
    zones = [raw.get(f"hrTimeInZone_{i}") for i in range(1, 6)]
    cadence = raw.get("averageRunningCadenceInStepsPerMinute") or raw.get("averageBikingCadenceInRevPerMinute")
    temps = [t for t in (raw.get("minTemperature"), raw.get("maxTemperature")) if t is not None]
    return ActivitySummary(
        activity_id=str(raw.get("activityId")),
        name=raw.get("activityName", "Atividade"),
        sport=(raw.get("activityType") or {}).get("typeKey", "other"),
        date=(raw.get("startTimeLocal") or "")[:10],
        start_time=(raw.get("startTimeLocal") or "")[11:16] or None,
        distance_km=round(distance_m / 1000, 2),
        duration_min=round(duration_s / 60, 1),
        avg_hr=_int_or_none(raw.get("averageHR")),
        max_hr=_int_or_none(raw.get("maxHR")),
        avg_pace_min_per_km=_pace_min_per_km(distance_m, duration_s),
        elevation_gain_m=raw.get("elevationGain"),
        aerobic_training_effect=_round_or_none(raw.get("aerobicTrainingEffect")),
        anaerobic_training_effect=_round_or_none(raw.get("anaerobicTrainingEffect")),
        training_effect_label=raw.get("trainingEffectLabel"),
        avg_cadence=_int_or_none(cadence),
        avg_temperature_c=round(sum(temps) / len(temps), 1) if temps else None,
        calories=raw.get("calories"),
        vo2max=raw.get("vO2MaxValue"),
        hr_time_in_zones_s=[z or 0.0 for z in zones] if any(z is not None for z in zones) else None,
        workout_id=str(raw["workoutId"]) if raw.get("workoutId") else None,
    )


def _summarize_laps(splits: dict[str, Any]) -> list[Lap]:
    laps = []
    for i, lap in enumerate(splits.get("lapDTOs") or [], start=1):
        laps.append(
            Lap(
                index=i,
                kind=lap.get("intensityType"),
                distance_km=round((lap.get("distance") or 0) / 1000, 2),
                duration_min=round((lap.get("duration") or 0) / 60, 1),
                pace_min_per_km=_pace_from_speed(lap.get("averageMovingSpeed") or lap.get("averageSpeed")),
                avg_hr=_int_or_none(lap.get("averageHR")),
                max_hr=_int_or_none(lap.get("maxHR")),
                cadence=_int_or_none(lap.get("averageRunCadence")),
            )
        )
    return laps


def _decoupling(laps: list[Lap]) -> float | None:
    """Aerobic decoupling (Pa:HR) entre a 1a e a 2a metade (por tempo) da parte principal."""
    main = [
        lap for lap in laps
        if lap.kind not in ("WARMUP", "COOLDOWN") and lap.avg_hr and lap.pace_min_per_km and lap.duration_min >= 1
    ]
    total = sum(lap.duration_min for lap in main)
    if len(main) < 2 or total < 20:
        return None

    halves: list[list[Lap]] = [[], []]
    elapsed = 0.0
    for lap in main:
        halves[0 if elapsed + lap.duration_min / 2 <= total / 2 else 1].append(lap)
        elapsed += lap.duration_min
    if not halves[0] or not halves[1]:
        return None

    def efficiency(group: list[Lap]) -> float:
        minutes = sum(lap.duration_min for lap in group)
        speed = sum((1 / lap.pace_min_per_km) * lap.duration_min for lap in group) / minutes
        hr = sum(lap.avg_hr * lap.duration_min for lap in group) / minutes
        return speed / hr

    first, second = efficiency(halves[0]), efficiency(halves[1])
    return round((first - second) / first * 100, 1)


def _target_text(step: dict[str, Any]) -> str:
    target = (step.get("targetType") or {}).get("workoutTargetTypeKey")
    one, two = step.get("targetValueOne"), step.get("targetValueTwo")
    if target == "pace.zone" and one and two:
        fast, slow = sorted((_pace_from_speed(one), _pace_from_speed(two)))
        return f"pace {fmt_pace(fast)}-{fmt_pace(slow)}/km"
    if target == "heart.rate.zone":
        if step.get("zoneNumber"):
            return f"FC zona {step['zoneNumber']}"
        if one and two:
            return f"FC {int(one)}-{int(two)} bpm"
    if target and target != "no.target":
        return f"alvo {target}"
    return "sem alvo"


def _duration_text(step: dict[str, Any]) -> str:
    condition = (step.get("endCondition") or {}).get("conditionTypeKey")
    value = step.get("endConditionValue")
    if condition == "time" and value:
        return f"{round(value / 60)} min"
    if condition == "distance" and value:
        return f"{value / 1000:g} km"
    return condition or "?"


def _render_steps(steps: list[dict[str, Any]], indent: str = "") -> list[str]:
    lines = []
    for step in steps:
        if step.get("type") == "RepeatGroupDTO":
            lines.append(f"{indent}- repetir {step.get('numberOfIterations')}x:")
            lines.extend(_render_steps(step.get("workoutSteps") or [], indent + "  "))
            continue
        kind = (step.get("stepType") or {}).get("stepTypeKey", "step")
        note = (step.get("description") or "").replace("\n", " ").strip()
        line = f"{indent}- {kind}: {_duration_text(step)}, {_target_text(step)}"
        lines.append(f"{line} ({note})" if note else line)
    return lines


def render_planned_workout(workout: dict[str, Any]) -> str:
    """Treino prescrito (agendado no Garmin) em texto legivel."""
    header = workout.get("workoutName") or "Treino"
    if workout.get("description"):
        header += f" - {workout['description']}"
    lines = [header]
    for segment in workout.get("workoutSegments") or []:
        lines.extend(_render_steps(segment.get("workoutSteps") or []))
    return "\n".join(lines)


def build_activity_detail(
    raw: dict[str, Any], splits: dict[str, Any] | None, planned_workout: dict[str, Any] | None
) -> ActivityDetail:
    laps = _summarize_laps(splits or {})
    return ActivityDetail(
        summary=summarize_activity(raw),
        laps=laps,
        decoupling_percent=_decoupling(laps),
        planned_workout_md=render_planned_workout(planned_workout) if planned_workout else None,
    )


def render_activity_detail_markdown(detail: ActivityDetail) -> str:
    s = detail.summary
    lines = [
        f"### {s.date} {s.start_time or ''} - {s.name} ({s.sport})",
        f"- Distancia: {s.distance_km} km | Duracao: {s.duration_min} min | Pace medio: {fmt_pace(s.avg_pace_min_per_km)}/km",
        f"- FC media/max: {s.avg_hr or '-'} / {s.max_hr or '-'} bpm | Cadencia: {s.avg_cadence or '-'} ppm",
        f"- Training effect aerobico/anaerobico: {s.aerobic_training_effect or '-'} / {s.anaerobic_training_effect or '-'}"
        f" ({s.training_effect_label or '-'})",
        f"- Temperatura: {s.avg_temperature_c or '-'} C | Elevacao: {s.elevation_gain_m or '-'} m | "
        f"Calorias: {s.calories or '-'} | VO2max estimado: {s.vo2max or '-'}",
    ]
    if s.hr_time_in_zones_s:
        zones = " | ".join(f"Z{i}: {round(sec / 60)} min" for i, sec in enumerate(s.hr_time_in_zones_s, start=1))
        lines.append(f"- Tempo por zona de FC (zonas do relogio): {zones}")
    if detail.decoupling_percent is not None:
        lines.append(f"- Desacoplamento pace:FC (1a x 2a metade): {detail.decoupling_percent}%")
    if detail.planned_workout_md:
        lines.append("\nTreino prescrito:")
        lines.append(detail.planned_workout_md)
    if detail.laps:
        lines.append("\n| Volta | Tipo | Dist (km) | Dur (min) | Pace | FC media | FC max | Cadencia |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for lap in detail.laps:
            lines.append(
                f"| {lap.index} | {lap.kind or '-'} | {lap.distance_km} | {lap.duration_min} | "
                f"{fmt_pace(lap.pace_min_per_km)} | {lap.avg_hr or '-'} | {lap.max_hr or '-'} | {lap.cadence or '-'} |"
            )
    return "\n".join(lines)


def render_summaries_markdown(summaries: list[ActivitySummary]) -> str:
    if not summaries:
        return "Nenhuma atividade nova desde a ultima sincronizacao."

    lines = ["| Data | Nome | Esporte | Dist (km) | Dur (min) | FC media | FC max | Pace (min/km) | TE aerobico | TE anaerobico |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for s in summaries:
        lines.append(
            f"| {s.date} | {s.name} | {s.sport} | {s.distance_km} | {s.duration_min} | "
            f"{s.avg_hr or '-'} | {s.max_hr or '-'} | {fmt_pace(s.avg_pace_min_per_km)} | "
            f"{s.aerobic_training_effect or '-'} | {s.anaerobic_training_effect or '-'} |"
        )
    return "\n".join(lines)
