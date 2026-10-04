from __future__ import annotations

import html
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from .config import AppConfig
from .metrics import ActivityDetail, fmt_pace
from .plan_schema import ActivityAnalysis, CoachResponse, MorningReport, TrainerReview

if TYPE_CHECKING:
    from .pipeline import SyncResult
    from .wellness import WellnessDay

FOOTER = (
    "Lembrete: o treinador Greg (Garmin Coach) e quem define os treinos. Este email e so "
    "acompanhamento/analise, gerado automaticamente pelo garmin-trainer."
)


def _send_email(config: AppConfig, subject: str, body: str, html_body: str | None = None) -> None:
    if not config.smtp_user or not config.smtp_password or not config.email_to:
        raise RuntimeError(
            "Email nao configurado. Preencha SMTP_USER, SMTP_PASSWORD e (opcional) EMAIL_TO no .env."
        )

    msg = MIMEMultipart("alternative")
    msg["From"] = config.smtp_user
    msg["To"] = config.email_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=60) as server:
        server.starttls()
        server.login(config.smtp_user, config.smtp_password)
        server.send_message(msg)


# ---------------------------------------------------------------------------
# Blocos HTML (estilos inline: o Gmail ignora <style> em varios clientes)
# ---------------------------------------------------------------------------

_INK = "#1f2933"
_MUTED = "#6b7280"
_LINE = "#e5e7eb"
_CHIP_COLORS = {
    "alta": "#15803d", "leve": "#15803d",
    "moderada": "#b45309", "moderado": "#b45309",
    "baixa": "#b91c1c", "forte": "#c2410c", "muito forte": "#b91c1c",
}
_ZONE_COLORS = ["#9ca3af", "#3b82f6", "#22c55e", "#f59e0b", "#ef4444"]


def _esc(value: object) -> str:
    return html.escape(str(value))


def _text_html(text: str | None) -> str:
    """Texto livre da IA -> paragrafos/listas simples."""
    if not text:
        return ""
    parts = []
    for block in text.strip().split("\n\n"):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if lines and all(ln.startswith(("- ", "* ", "• ")) for ln in lines):
            items = "".join(f"<li style='margin:2px 0'>{_esc(ln[2:])}</li>" for ln in lines)
            parts.append(f"<ul style='margin:6px 0;padding-left:20px'>{items}</ul>")
        else:
            parts.append(f"<p style='margin:6px 0;line-height:1.5'>{'<br>'.join(_esc(ln) for ln in lines)}</p>")
    return "".join(parts)


def _section(title: str, inner_html: str) -> str:
    if not inner_html:
        return ""
    return (
        f"<h2 style='font-size:16px;margin:22px 0 6px;color:{_INK};border-bottom:1px solid {_LINE};"
        f"padding-bottom:4px'>{_esc(title)}</h2>{inner_html}"
    )


def _chip(label: str) -> str:
    color = _CHIP_COLORS.get(label.lower(), _MUTED)
    return (
        f"<span style='display:inline-block;background:{color};color:#fff;border-radius:12px;"
        f"padding:2px 10px;font-size:12px;font-weight:bold'>{_esc(label.upper())}</span>"
    )


def _cards(cards: list[tuple[str, str, str]], per_row: int = 3) -> str:
    """cards: (rotulo, valor, subtitulo)."""
    cards = [c for c in cards if c[1] not in ("", "-", "None")]
    rows = []
    for i in range(0, len(cards), per_row):
        cells = "".join(
            f"<td width='{100 // per_row}%' style='padding:4px;vertical-align:top'>"
            f"<div style='border:1px solid {_LINE};border-radius:8px;padding:8px 10px'>"
            f"<div style='font-size:11px;color:{_MUTED};text-transform:uppercase'>{_esc(label)}</div>"
            f"<div style='font-size:20px;font-weight:bold;color:{_INK}'>{_esc(value)}</div>"
            f"<div style='font-size:12px;color:{_MUTED}'>{_esc(sub)}</div></div></td>"
            for label, value, sub in cards[i:i + per_row]
        )
        rows.append(f"<tr>{cells}</tr>")
    return f"<table width='100%' cellspacing='0' cellpadding='0'>{''.join(rows)}</table>"


def _table(headers: list[str], rows: list[list[object]]) -> str:
    head = "".join(
        f"<th style='text-align:left;padding:4px 6px;border-bottom:2px solid {_LINE};font-size:12px;color:{_MUTED}'>{_esc(h)}</th>"
        for h in headers
    )
    body = "".join(
        "<tr>" + "".join(
            f"<td style='padding:4px 6px;border-bottom:1px solid {_LINE};font-size:13px'>{_esc('-' if c is None else c)}</td>"
            for c in row
        ) + "</tr>"
        for row in rows
    )
    return f"<table cellspacing='0' cellpadding='0' style='border-collapse:collapse;width:100%'><tr>{head}</tr>{body}</table>"


def _zone_bar(seconds: list[float]) -> str:
    total = sum(seconds) or 1
    cells = "".join(
        f"<td style='background:{_ZONE_COLORS[i]};height:14px;padding:0' width='{max(sec / total * 100, 0.5):.1f}%'></td>"
        for i, sec in enumerate(seconds) if sec > 0
    )
    legend = " &nbsp; ".join(
        f"<span style='color:{_ZONE_COLORS[i]}'>&#9632;</span> Z{i + 1} {round(sec / 60)} min ({sec / total:.0%})"
        for i, sec in enumerate(seconds)
    )
    return (
        f"<table width='100%' cellspacing='0' cellpadding='0' style='border-radius:4px;overflow:hidden'><tr>{cells}</tr></table>"
        f"<div style='font-size:12px;color:{_MUTED};margin-top:4px'>{legend}</div>"
    )


def _page(title: str, subtitle: str, content: str) -> str:
    return f"""<!doctype html><html><body style="margin:0;background:#f3f4f6;font-family:Arial,Helvetica,sans-serif;color:{_INK}">
<div style="max-width:680px;margin:0 auto;background:#fff;padding:20px 22px">
<h1 style="font-size:20px;margin:0">{_esc(title)}</h1>
<div style="font-size:13px;color:{_MUTED};margin:4px 0 8px">{_esc(subtitle)}</div>
{content}
<p style="font-size:11px;color:{_MUTED};margin-top:28px;border-top:1px solid {_LINE};padding-top:8px">{_esc(FOOTER)}</p>
</div></body></html>"""


def _fmt(value: object, suffix: str = "") -> str:
    return "-" if value is None else f"{value}{suffix}"


# ---------------------------------------------------------------------------
# Email de atividade
# ---------------------------------------------------------------------------

def send_activity_report(
    config: AppConfig, detail: ActivityDetail, analysis: ActivityAnalysis | None, error: str | None
) -> None:
    s = detail.summary
    when = f"{s.date} {s.start_time or ''}".strip()
    cards = _cards([
        ("Distancia", f"{s.distance_km} km", f"{s.duration_min} min"),
        ("Pace medio", f"{fmt_pace(s.avg_pace_min_per_km)}/km", f"cadencia {_fmt(s.avg_cadence, ' ppm')}"),
        ("FC media", _fmt(s.avg_hr, " bpm"), f"max {_fmt(s.max_hr, ' bpm')}"),
        ("Training effect", _fmt(s.aerobic_training_effect), f"anaerobico {_fmt(s.anaerobic_training_effect)}"),
        ("Desacoplamento", _fmt(detail.decoupling_percent, "%"), "pace:FC, ideal < 5%"),
        ("Temperatura", _fmt(s.avg_temperature_c, " C"), f"{_fmt(s.calories)} kcal"),
    ])

    parts = [cards]
    if analysis:
        parts.insert(0, f"<p style='font-size:15px;margin:10px 0'>{_chip(analysis.effort_rating)} &nbsp;"
                        f"<b>{_esc(analysis.headline)}</b></p>")
        parts += [
            _section("Prescrito x executado", _text_html(analysis.execution_vs_plan)),
            _section("Frequencia cardiaca", _text_html(analysis.heart_rate_analysis)),
            _section("Ritmo", _text_html(analysis.pacing_analysis)),
            _section("O que foi bem", _text_html(analysis.highlights)),
            _section("Pontos de atencao", _text_html(analysis.attention_points)),
            _section("Recuperacao", _text_html(analysis.recovery_tips)),
        ]
    else:
        parts.append(f"<p style='color:{_MUTED}'>Analise da IA indisponivel ({_esc(error or 'erro desconhecido')}). "
                     "Seguem so os dados.</p>")
    if s.hr_time_in_zones_s:
        parts.append(_section("Tempo por zona de FC (zonas do relogio)", _zone_bar(s.hr_time_in_zones_s)))
    if detail.planned_workout_md:
        parts.append(_section("Treino do Greg",
                              f"<pre style='font-size:12px;background:#f9fafb;padding:8px;white-space:pre-wrap'>"
                              f"{_esc(detail.planned_workout_md)}</pre>"))
    if detail.laps:
        parts.append(_section("Voltas", _table(
            ["#", "Tipo", "Km", "Min", "Pace", "FC med", "FC max", "Cad"],
            [[lap.index, (lap.kind or "-").lower(), lap.distance_km, lap.duration_min, fmt_pace(lap.pace_min_per_km),
              lap.avg_hr, lap.max_hr, lap.cadence] for lap in detail.laps],
        )))

    text = [f"{s.name} - {when}", f"{s.distance_km} km | {s.duration_min} min | pace {fmt_pace(s.avg_pace_min_per_km)}/km | "
            f"FC {_fmt(s.avg_hr)}/{_fmt(s.max_hr)}"]
    if analysis:
        text += ["", analysis.headline, "", "Prescrito x executado:", analysis.execution_vs_plan, "",
                 "FC:", analysis.heart_rate_analysis, "", "Ritmo:", analysis.pacing_analysis, "",
                 "O que foi bem:", analysis.highlights, "", "Atencao:", analysis.attention_points, "",
                 "Recuperacao:", analysis.recovery_tips]
    text += ["", "--", FOOTER]

    _send_email(
        config,
        f"Treino {s.date}: {s.name} ({s.distance_km} km, {fmt_pace(s.avg_pace_min_per_km)}/km)",
        "\n".join(text),
        _page(s.name, f"{when} · {s.sport}", "".join(parts)),
    )


# ---------------------------------------------------------------------------
# Relatorio matinal
# ---------------------------------------------------------------------------

def send_morning_report(
    config: AppConfig,
    days: list[WellnessDay],
    report: MorningReport | None,
    error: str | None,
) -> None:
    today_str = date.today().isoformat()
    today = next((d for d in days if d.date == today_str), None)
    yesterday = next((d for d in reversed(days) if d.date < today_str), None)

    cards: list[tuple[str, str, str]] = []
    if today:
        cards += [
            ("Sono", _fmt(today.sleep_score), f"{_fmt(today.sleep_hours, ' h')} · {(today.sleep_quality or '').lower()}"),
            ("Fases do sono", f"{_fmt(today.deep_sleep_min)} / {_fmt(today.rem_sleep_min)}", "min profundo / REM"),
            ("HRV noite", _fmt(today.hrv_last_night_avg, " ms"),
             f"faixa {_fmt(today.hrv_baseline_low)}-{_fmt(today.hrv_baseline_high)} · {(today.hrv_status or '').lower()}"),
            ("FC repouso", _fmt(today.resting_hr or (yesterday.resting_hr if yesterday else None), " bpm"),
             f"media 7d {_fmt(today.rhr_7d_avg or (yesterday.rhr_7d_avg if yesterday else None))}"),
            ("Body battery", _fmt(today.body_battery_at_wake), "ao acordar"),
        ]
    if yesterday:
        cards += [
            ("Estresse ontem", _fmt(yesterday.avg_stress), f"{_fmt(yesterday.high_stress_min)} min em estresse alto"),
            ("Passos ontem", f"{yesterday.steps:,}".replace(",", ".") if yesterday.steps else "-",
             f"meta {_fmt(yesterday.step_goal)}"),
            ("Intensidade ontem", f"{(yesterday.intensity_min_moderate or 0) + 2 * (yesterday.intensity_min_vigorous or 0)} min",
             f"{_fmt(yesterday.intensity_min_moderate)} mod / {_fmt(yesterday.intensity_min_vigorous)} vig"),
        ]
    weight = next((d.weight_kg for d in reversed(days) if d.weight_kg), None)
    if weight:
        cards.append(("Peso", f"{weight} kg", "ultimo registro"))

    parts = []
    if report:
        parts.append(f"<p style='font-size:15px;margin:10px 0'>Prontidao {_chip(report.readiness)} &nbsp;"
                     f"<b>{_esc(report.headline)}</b></p>")
    parts.append(_cards(cards))
    if report:
        parts += [
            _section("Sono", _text_html(report.sleep_analysis)),
            _section("Recuperacao", _text_html(report.recovery_analysis)),
            _section("Seu dia ontem", _text_html(report.yesterday_analysis)),
            _section("Tendencias da semana", _text_html(report.trends)),
            _section("Objetivos", _text_html(report.goals)),
            _section("Dicas para hoje", _text_html(report.tips_for_today)),
        ]
    else:
        parts.append(f"<p style='color:{_MUTED}'>Analise da IA indisponivel ({_esc(error or 'erro desconhecido')}). "
                     "Seguem so as metricas.</p>")
    parts.append(_section("Ultimos 7 dias", _table(
        ["Data", "Sono", "Horas", "HRV", "FC rep", "BB acordar", "Estresse", "Passos"],
        [[d.date[5:], d.sleep_score, d.sleep_hours, d.hrv_last_night_avg, d.resting_hr, d.body_battery_at_wake,
          d.avg_stress, d.steps] for d in days],
    )))

    text = [f"Relatorio matinal - {today_str}"]
    if report:
        text += [f"Prontidao: {report.readiness} - {report.headline}", "", "Sono:", report.sleep_analysis, "",
                 "Recuperacao:", report.recovery_analysis, "", "Ontem:", report.yesterday_analysis, "",
                 "Tendencias:", report.trends, "", "Objetivos:", report.goals, "", "Dicas:", report.tips_for_today]
    else:
        text.append(f"Analise indisponivel: {error}")
    text += ["", "--", FOOTER]

    subject = f"Bom dia! Prontidao {report.readiness} - {today_str}" if report else f"Relatorio matinal - {today_str}"
    _send_email(config, subject, "\n".join(text), _page("Relatorio matinal", today_str, "".join(parts)))


# ---------------------------------------------------------------------------
# Emails legados / sob demanda (texto simples)
# ---------------------------------------------------------------------------

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
    _send_email(
        config,
        f"Garmin Trainer - Relatorio {date.today().isoformat()}",
        _build_body(plan, sync_result),
    )


def send_failure_alert(config: AppConfig, log_excerpt: str) -> None:
    """Avisa por email quando a execucao agendada falha.

    Sem isso, uma falha (login quebrado, dependencia faltando) fica silenciosa: o atleta so
    percebe quando nota a ausencia dos emails. O chamador limita a um alerta por dia.
    """
    if not config.smtp_user or not config.smtp_password or not config.email_to:
        return

    body = f"""A execucao automatica do garmin-trainer falhou hoje.

Ultimas linhas do log:
{log_excerpt}

--
Gerado automaticamente pelo garmin-trainer.
"""
    _send_email(config, f"Garmin Trainer - FALHA na execucao de {date.today().isoformat()}", body)


def _build_review_body(review: TrainerReview, activity_summary_md: str) -> str:
    return f"""Garmin Trainer - Analise do personal trainer — {date.today().isoformat()}

## Atividades analisadas
{activity_summary_md}

## Resumo
{review.summary}

## O que evoluiu
{review.highlights}

## Pontos de atencao
{review.improvement_areas}

## Recuperacao e peso
{review.recovery_assessment}

--
{FOOTER}
"""


def send_review_report(config: AppConfig, review: TrainerReview, activity_summary_md: str) -> None:
    _send_email(
        config,
        f"Garmin Trainer - Analise do treinador {date.today().isoformat()}",
        _build_review_body(review, activity_summary_md),
    )
