from __future__ import annotations

from pathlib import Path
from typing import Any

from garminconnect import Garmin
from garminconnect.workout import (
    BaseWorkout,
    CyclingWorkout,
    RunningWorkout,
)

from .config import AppConfig, PROJECT_ROOT
from .retry import call_with_retry

RUNNING_TYPES = {"running"}
CYCLING_TYPES = {"cycling"}


class GarminClient:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self.api = Garmin(
            config.garmin_email,
            config.garmin_password,
            prompt_mfa=lambda: input("Codigo MFA do Garmin Connect: "),
        )

    def login(self) -> None:
        call_with_retry(lambda: self.api.login(self._config.token_store))

    def recent_activities(self, limit: int = 10, activity_type: str | None = None) -> list[dict[str, Any]]:
        result = self.api.get_activities(start=0, limit=limit, activitytype=activity_type)
        return result if isinstance(result, list) else result.get("activities", [])

    def activity_detail(self, activity_id: str) -> dict[str, Any]:
        return self.api.get_activity(activity_id)

    def activity_splits(self, activity_id: str) -> dict[str, Any]:
        return self.api.get_activity_splits(activity_id)

    def sleep_data(self, date_str: str) -> dict[str, Any]:
        return self.api.get_sleep_data(date_str)

    def stress_data(self, date_str: str) -> dict[str, Any]:
        return self.api.get_all_day_stress(date_str)

    def hrv_data(self, date_str: str) -> dict[str, Any] | None:
        return self.api.get_hrv_data(date_str)

    def resting_hr(self, date_str: str) -> dict[str, Any]:
        return self.api.get_rhr_day(date_str)

    def download_tcx(self, activity_id: str, dest_dir: Path | None = None) -> Path:
        dest_dir = dest_dir or (PROJECT_ROOT / "data" / "activities")
        dest_dir.mkdir(parents=True, exist_ok=True)
        payload = self.api.download_activity(
            activity_id, dl_fmt=Garmin.ActivityDownloadFormat.TCX
        )
        dest_path = dest_dir / f"{activity_id}.tcx"
        dest_path.write_bytes(payload)
        return dest_path

    def upload_and_schedule(self, workout: BaseWorkout, sport: str, date_str: str) -> dict[str, Any]:
        if sport in RUNNING_TYPES:
            assert isinstance(workout, RunningWorkout)
            uploaded = self.api.upload_running_workout(workout)
        elif sport in CYCLING_TYPES:
            assert isinstance(workout, CyclingWorkout)
            uploaded = self.api.upload_cycling_workout(workout)
        else:
            raise ValueError(f"Esporte nao suportado ainda: {sport}")

        workout_id = uploaded.get("workoutId") or uploaded.get("workoutSummary", {}).get("workoutId")
        if workout_id is None:
            raise RuntimeError(f"Nao consegui extrair workoutId da resposta do Garmin: {uploaded}")
        self.api.schedule_workout(workout_id, date_str)
        return uploaded
