from __future__ import annotations

import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from .config import AppConfig
from .plan_schema import CoachResponse

if TYPE_CHECKING:
    from .pipeline import SyncResult


def _build_body(plan: CoachResponse, sync_result: SyncResult) -> str:
    workouts_lines = []
    for w in plan.planned_workouts:
        workouts_lines.append(f"- {w.date} [{w.sport}] {w.name}")
        workouts_lines.append(f"  {w.description}")
    workouts_block = "\n".join(workouts_lines) if workouts_lines else "(nenhum treino novo)"

    return f"""Relatorio Garmin Trainer — {date.today().isoformat()}

## Atividades desde o ultimo ciclo
{sync_result.summaries_md}

## O que melhorou
{plan.highlights}

## Pontos de atencao
{plan.improvement_areas}

## Recuperacao (sono, estresse, HRV)
{plan.recovery_assessment}

## Metricas e alvos para os proximos treinos
{plan.next_targets}

## Resumo da analise
{plan.analysis}

## Treinos publicados no Garmin Connect
{workouts_block}

--
Gerado automaticamente pelo garmin-trainer.
"""


def send_report(config: AppConfig, plan: CoachResponse, sync_result: SyncResult) -> None:
    if not config.smtp_user or not config.smtp_password or not config.email_to:
        raise RuntimeError(
            "Email nao configurado. Preencha SMTP_USER, SMTP_PASSWORD e (opcional) EMAIL_TO no .env."
        )

    msg = MIMEMultipart()
    msg["From"] = config.smtp_user
    msg["To"] = config.email_to
    msg["Subject"] = f"Garmin Trainer - Relatorio {date.today().isoformat()}"
    msg.attach(MIMEText(_build_body(plan, sync_result), "plain", "utf-8"))

    with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
        server.starttls()
        server.login(config.smtp_user, config.smtp_password)
        server.send_message(msg)


def send_failure_alert(config: AppConfig, log_excerpt: str) -> None:
    """Avisa por email quando a execucao agendada falha antes de gerar o relatorio normal.

    Sem isso, uma falha (login quebrado, path invalido, dependencia faltando) fica
    silenciosa: o atleta so percebe quando nota a ausencia do email de insights.
    """
    if not config.smtp_user or not config.smtp_password or not config.email_to:
        return

    msg = MIMEMultipart()
    msg["From"] = config.smtp_user
    msg["To"] = config.email_to
    msg["Subject"] = f"Garmin Trainer - FALHA na execucao de {date.today().isoformat()}"
    body = f"""O pipeline automatico do garmin-trainer falhou hoje e nao gerou o relatorio de insights.

Ultimas linhas do log:
{log_excerpt}

--
Gerado automaticamente pelo garmin-trainer.
"""
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
        server.starttls()
        server.login(config.smtp_user, config.smtp_password)
        server.send_message(msg)
