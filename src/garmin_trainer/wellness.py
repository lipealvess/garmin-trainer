from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel

from .garmin_client import GarminClient


class WellnessDay(BaseModel):
    date: str
    sleep_score: int | None = None
    sleep_hours: float | None = None
    avg_sleep_stress: float | None = None
    avg_stress: int | None = None
    max_stress: int | None = None
    hrv_status: str | None = None
    hrv_last_night_avg: int | None = None
    resting_hr: float | None = None

    def has_data(self) -> bool:
        return any(
            v is not None
            for v in (
                self.sleep_score,
                self.avg_stress,
                self.hrv_status,
                self.resting_hr,
            )
        )


def _safe_sleep(client: GarminClient, date_str: str) -> tuple[int | None, float | None, float | None]:
    try:
        dto = client.sleep_data(date_str).get("dailySleepDTO") or {}
        score = (dto.get("sleepScores") or {}).get("overall", {}).get("value")
        seconds = dto.get("sleepTimeSeconds")
        hours = round(seconds / 3600, 1) if seconds else None
        return score, hours, dto.get("avgSleepStress")
    except Exception:
        return None, None, None


def _safe_stress(client: GarminClient, date_str: str) -> tuple[int | None, int | None]:
    try:
        data = client.stress_data(date_str)
        return data.get("avgStressLevel"), data.get("maxStressLevel")
    except Exception:
        return None, None


def _safe_hrv(client: GarminClient, date_str: str) -> tuple[str | None, int | None]:
    try:
        data = client.hrv_data(date_str)
        summary = (data or {}).get("hrvSummary") or {}
        return summary.get("status"), summary.get("lastNightAvg")
    except Exception:
        return None, None


def _safe_rhr(client: GarminClient, date_str: str) -> float | None:
    try:
        data = client.resting_hr(date_str)
        values = data.get("allMetrics", {}).get("metricsMap", {}).get("WELLNESS_RESTING_HEART_RATE") or []
        return values[0].get("value") if values else None
    except Exception:
        return None


def fetch_wellness(client: GarminClient, days: int = 3) -> list[WellnessDay]:
    result = []
    for offset in range(days):
        d = (date.today() - timedelta(days=offset)).isoformat()
        sleep_score, sleep_hours, avg_sleep_stress = _safe_sleep(client, d)
        avg_stress, max_stress = _safe_stress(client, d)
        hrv_status, hrv_avg = _safe_hrv(client, d)
        rhr = _safe_rhr(client, d)
        day = WellnessDay(
            date=d,
            sleep_score=sleep_score,
            sleep_hours=sleep_hours,
            avg_sleep_stress=avg_sleep_stress,
            avg_stress=avg_stress,
            max_stress=max_stress,
            hrv_status=hrv_status,
            hrv_last_night_avg=hrv_avg,
            resting_hr=rhr,
        )
        if day.has_data():
            result.append(day)
    return list(reversed(result))


def render_wellness_markdown(days: list[WellnessDay]) -> str:
    if not days:
        return "Sem dados de sono/estresse/HRV disponiveis para o periodo."

    lines = [
        "| Data | Sono (score) | Sono (h) | Estresse medio | Estresse max | HRV status | HRV medio (ms) | FC repouso |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for d in days:
        lines.append(
            f"| {d.date} | {d.sleep_score or '-'} | {d.sleep_hours or '-'} | "
            f"{d.avg_stress if d.avg_stress is not None else '-'} | {d.max_stress if d.max_stress is not None else '-'} | "
            f"{d.hrv_status or '-'} | {d.hrv_last_night_avg or '-'} | {d.resting_hr or '-'} |"
        )
    return "\n".join(lines)
