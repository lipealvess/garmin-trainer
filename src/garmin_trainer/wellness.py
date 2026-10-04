from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel

from .garmin_client import GarminClient


class WellnessDay(BaseModel):
    """Metricas de um dia D.

    Sono e HRV sao da noite que TERMINOU na manha de D (como o Garmin registra). As metricas
    de dia (passos, estresse, body battery, FC) cobrem o dia D inteiro - entao, para o dia de
    hoje, ainda sao parciais.
    """

    date: str
    # Sono (noite que terminou em D)
    sleep_score: int | None = None
    sleep_quality: str | None = None
    sleep_hours: float | None = None
    deep_sleep_min: int | None = None
    light_sleep_min: int | None = None
    rem_sleep_min: int | None = None
    awake_min: int | None = None
    avg_sleep_stress: float | None = None
    sleep_avg_hr: int | None = None
    sleep_feedback: str | None = None
    # HRV (noite que terminou em D)
    hrv_status: str | None = None
    hrv_last_night_avg: int | None = None
    hrv_weekly_avg: int | None = None
    hrv_baseline_low: int | None = None
    hrv_baseline_high: int | None = None
    # Dia D (resumo diario do relogio)
    resting_hr: int | None = None
    rhr_7d_avg: int | None = None
    min_hr: int | None = None
    max_hr: int | None = None
    avg_stress: int | None = None
    max_stress: int | None = None
    high_stress_min: int | None = None
    stress_qualifier: str | None = None
    body_battery_at_wake: int | None = None
    body_battery_high: int | None = None
    body_battery_low: int | None = None
    body_battery_charged: int | None = None
    body_battery_drained: int | None = None
    steps: int | None = None
    step_goal: int | None = None
    active_kcal: int | None = None
    intensity_min_moderate: int | None = None
    intensity_min_vigorous: int | None = None
    avg_waking_respiration: float | None = None
    weight_kg: float | None = None

    def has_data(self) -> bool:
        return any(
            v is not None
            for v in (self.sleep_score, self.avg_stress, self.hrv_status, self.resting_hr, self.steps, self.weight_kg)
        )

    def has_sleep(self) -> bool:
        return self.sleep_score is not None or self.sleep_hours is not None


def _minutes(seconds: float | None) -> int | None:
    return round(seconds / 60) if seconds is not None else None


def _sleep_fields(client: GarminClient, date_str: str) -> dict[str, Any]:
    try:
        dto = client.sleep_data(date_str).get("dailySleepDTO") or {}
    except Exception:
        return {}
    if not dto.get("sleepTimeSeconds"):
        return {}
    overall = (dto.get("sleepScores") or {}).get("overall") or {}
    return {
        "sleep_score": overall.get("value"),
        "sleep_quality": overall.get("qualifierKey"),
        "sleep_hours": round(dto["sleepTimeSeconds"] / 3600, 1),
        "deep_sleep_min": _minutes(dto.get("deepSleepSeconds")),
        "light_sleep_min": _minutes(dto.get("lightSleepSeconds")),
        "rem_sleep_min": _minutes(dto.get("remSleepSeconds")),
        "awake_min": _minutes(dto.get("awakeSleepSeconds")),
        "avg_sleep_stress": dto.get("avgSleepStress"),
        "sleep_avg_hr": round(dto["avgHeartRate"]) if dto.get("avgHeartRate") else None,
        "sleep_feedback": dto.get("sleepScoreFeedback"),
    }


def has_sleep_data(client: GarminClient, date_str: str) -> bool:
    return bool(_sleep_fields(client, date_str))


def _hrv_fields(client: GarminClient, date_str: str) -> dict[str, Any]:
    try:
        summary = (client.hrv_data(date_str) or {}).get("hrvSummary") or {}
    except Exception:
        return {}
    baseline = summary.get("baseline") or {}
    return {
        "hrv_status": summary.get("status"),
        "hrv_last_night_avg": summary.get("lastNightAvg"),
        "hrv_weekly_avg": summary.get("weeklyAvg"),
        "hrv_baseline_low": baseline.get("balancedLow"),
        "hrv_baseline_high": baseline.get("balancedUpper"),
    }


def _stats_fields(client: GarminClient, date_str: str) -> dict[str, Any]:
    try:
        s = client.daily_stats(date_str) or {}
    except Exception:
        return {}
    return {
        "resting_hr": s.get("restingHeartRate"),
        "rhr_7d_avg": s.get("lastSevenDaysAvgRestingHeartRate"),
        "min_hr": s.get("minHeartRate"),
        "max_hr": s.get("maxHeartRate"),
        "avg_stress": s.get("averageStressLevel") if (s.get("averageStressLevel") or 0) >= 0 else None,
        "max_stress": s.get("maxStressLevel") if (s.get("maxStressLevel") or 0) >= 0 else None,
        "high_stress_min": _minutes(s.get("highStressDuration")),
        "stress_qualifier": s.get("stressQualifier"),
        "body_battery_at_wake": s.get("bodyBatteryAtWakeTime"),
        "body_battery_high": s.get("bodyBatteryHighestValue"),
        "body_battery_low": s.get("bodyBatteryLowestValue"),
        "body_battery_charged": s.get("bodyBatteryChargedValue"),
        "body_battery_drained": s.get("bodyBatteryDrainedValue"),
        "steps": s.get("totalSteps"),
        "step_goal": s.get("dailyStepGoal"),
        "active_kcal": int(s["activeKilocalories"]) if s.get("activeKilocalories") is not None else None,
        "intensity_min_moderate": s.get("moderateIntensityMinutes"),
        "intensity_min_vigorous": s.get("vigorousIntensityMinutes"),
        "avg_waking_respiration": s.get("avgWakingRespirationValue"),
    }


def _weights_by_date(client: GarminClient, start: date, end: date) -> dict[str, float]:
    try:
        data = client.body_composition(start.isoformat(), end.isoformat()) or {}
    except Exception:
        return {}
    result: dict[str, float] = {}
    for entry in data.get("dateWeightList") or []:
        if entry.get("weight") and entry.get("calendarDate"):
            result[entry["calendarDate"]] = round(entry["weight"] / 1000, 1)
    return result


def fetch_wellness(client: GarminClient, days: int = 3, end: date | None = None) -> list[WellnessDay]:
    """Metricas dos ultimos `days` dias ate `end` (inclusive), em ordem cronologica."""
    end = end or date.today()
    start = end - timedelta(days=days - 1)
    weights = _weights_by_date(client, start, end)

    result = []
    for offset in range(days):
        d = (start + timedelta(days=offset)).isoformat()
        day = WellnessDay(
            date=d,
            weight_kg=weights.get(d),
            **_sleep_fields(client, d),
            **_hrv_fields(client, d),
            **_stats_fields(client, d),
        )
        if day.has_data():
            result.append(day)
    return result


def _v(value: Any) -> str:
    return "-" if value is None else str(value)


def render_wellness_markdown(days: list[WellnessDay]) -> str:
    """Tabelas compactas para o prompt da IA."""
    if not days:
        return "Sem dados de sono/estresse/HRV disponiveis para o periodo."

    sleep_lines = [
        "Sono e HRV (noite que terminou na data):",
        "| Data | Sono score | Sono (h) | Profundo (min) | REM (min) | Acordado (min) | Estresse no sono | FC no sono | HRV noite (ms) | HRV 7d (ms) | HRV faixa normal | HRV status |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    day_lines = [
        "Dia (resumo diario do relogio; o dia de hoje e parcial):",
        "| Data | FC repouso | FC repouso 7d | FC min/max | Estresse medio | Estresse alto (min) | Body battery acordar | BB max/min | Passos | Min. intensidade (mod/vig) | Kcal ativas | Peso (kg) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for d in days:
        baseline = f"{d.hrv_baseline_low}-{d.hrv_baseline_high}" if d.hrv_baseline_low else "-"
        sleep_lines.append(
            f"| {d.date} | {_v(d.sleep_score)} | {_v(d.sleep_hours)} | {_v(d.deep_sleep_min)} | {_v(d.rem_sleep_min)} | "
            f"{_v(d.awake_min)} | {_v(d.avg_sleep_stress)} | {_v(d.sleep_avg_hr)} | {_v(d.hrv_last_night_avg)} | "
            f"{_v(d.hrv_weekly_avg)} | {baseline} | {_v(d.hrv_status)} |"
        )
        day_lines.append(
            f"| {d.date} | {_v(d.resting_hr)} | {_v(d.rhr_7d_avg)} | {_v(d.min_hr)}/{_v(d.max_hr)} | {_v(d.avg_stress)} | "
            f"{_v(d.high_stress_min)} | {_v(d.body_battery_at_wake)} | {_v(d.body_battery_high)}/{_v(d.body_battery_low)} | "
            f"{_v(d.steps)} | {_v(d.intensity_min_moderate)}/{_v(d.intensity_min_vigorous)} | {_v(d.active_kcal)} | {_v(d.weight_kg)} |"
        )
    return "\n".join(sleep_lines) + "\n\n" + "\n".join(day_lines)
