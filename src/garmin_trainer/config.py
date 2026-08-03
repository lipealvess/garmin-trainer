from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = PROJECT_ROOT / "config" / "athlete_profile.yaml"


class ConfigError(RuntimeError):
    pass


class AppConfig:
    def __init__(self) -> None:
        load_dotenv(PROJECT_ROOT / ".env")

        self.garmin_email = os.getenv("GARMIN_EMAIL", "")
        self.garmin_password = os.getenv("GARMIN_PASSWORD", "")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.token_store = str(
            PROJECT_ROOT / os.getenv("GARMIN_TOKEN_STORE", ".garminconnect_tokens")
        )

        # Email de insights (opcional): so e exigido se --email for usado.
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.email_to = os.getenv("EMAIL_TO", self.smtp_user)

        if not self.garmin_email or not self.garmin_password:
            raise ConfigError(
                "GARMIN_EMAIL / GARMIN_PASSWORD nao configurados. Copie .env.example para .env e preencha."
            )
        if not self.gemini_api_key:
            raise ConfigError(
                "GEMINI_API_KEY nao configurada. Copie .env.example para .env e preencha."
            )


def load_profile() -> dict[str, Any]:
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_profile(profile: dict[str, Any]) -> None:
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(profile, f, allow_unicode=True, sort_keys=False)
