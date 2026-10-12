from __future__ import annotations

import json
import sys
from datetime import date

import click

from . import email_report
from .config import PROJECT_ROOT, AppConfig, load_profile
from .garmin_client import GarminClient
from .metrics import fmt_pace
from .pipeline import (
    TickResult,
    run_tick,
    run_trainer_review,
    run_week_plan,
    sync_activities,
)
from .state import load_state, save_state

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


@click.group()
def main() -> None:
    """garmin-trainer: plano semanal, analise de treinos e relatorio matinal (Garmin + Gemini)."""


@main.command()
def login_test() -> None:
    """Testa as credenciais do Garmin Connect e o cache de token."""
    config = AppConfig()
    client = GarminClient(config)
    client.login()
    click.echo(f"Login ok. Nome completo: {client.api.get_full_name()}")


@main.command()
@click.option("--limit", default=10, show_default=True, help="Quantidade de atividades recentes a considerar.")
def sync(limit: int) -> None:
    """Busca atividades novas no Garmin Connect desde a ultima sincronizacao e imprime um resumo."""
    config = AppConfig()
    profile = load_profile()
    client = GarminClient(config)
    client.login()

    result = sync_activities(client, profile, limit=limit)
    click.echo(result.summaries_md)


@main.command()
@click.option("--push", is_flag=True, default=False, help="Publica e agenda os treinos no relogio (substitui os futuros do plano anterior).")
@click.option("--email/--no-email", default=False, show_default=True, help="Envia o plano por email.")
@click.option("--start-date", default=None, help="Data de inicio (YYYY-MM-DD). Padrao: hoje (ou segunda, se hoje for domingo).")
def plan(push: bool, email: bool, start_date: str | None) -> None:
    """Gera o plano de treinos da semana. Sem --push e so um rascunho (nada vai para o relogio)."""
    config = AppConfig()
    client = GarminClient(config)
    client.login()
    parsed_start = date.fromisoformat(start_date) if start_date else None
    week_plan, start, end = run_week_plan(
        config, client, load_profile(), load_state(), client.recent_activities(limit=25),
        push=push, email=email, start_date=parsed_start,
    )

    out = PROJECT_ROOT / "data" / "plans" / f"plan_{start.isoformat()}.json"
    out.write_text(json.dumps(week_plan.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

    click.echo(f"=== Semana {start} a {end}: {week_plan.week_focus} ===")
    for w in week_plan.planned_workouts:
        click.echo(f"\n{w.date} - {w.name}")
        click.echo(f"  {w.description}")
        for line in email_report.describe_steps(w.steps):
            click.echo(f"    {line}")
    click.echo(f"\n=== Por que ===\n{week_plan.analysis}")
    click.echo(f"\n=== Recuperacao ===\n{week_plan.recovery_assessment}")
    click.echo(f"\nPlano salvo em {out}")
    click.echo("Publicado no Garmin." if push else "Rascunho: nada foi publicado. Use --push para publicar.")
    if email:
        click.echo(f"Email enviado para {config.email_to}.")


def _print_tick(result: TickResult, email: bool) -> None:
    if not result.activities:
        click.echo("Nenhuma atividade nova.")
    for item in result.activities:
        s = item.detail.summary
        click.echo(f"=== Atividade: {s.date} {s.name} ({s.distance_km} km, {fmt_pace(s.avg_pace_min_per_km)}/km) ===")
        click.echo(item.analysis.headline if item.analysis else f"Analise da IA indisponivel: {item.error}")
        if email:
            click.echo("Email da atividade enviado.")

    if result.plan:
        click.echo(f"=== Plano semanal publicado: {result.plan.week_focus} ({len(result.plan.planned_workouts)} treinos) ===")
    elif result.plan_error:
        click.echo(f"Plano semanal falhou (tenta de novo na proxima execucao): {result.plan_error}")

    if result.morning_skipped_reason:
        click.echo(f"Relatorio matinal: pulado ({result.morning_skipped_reason}).")
    elif result.morning:
        click.echo(f"=== Relatorio matinal (prontidao {result.morning.readiness}) ===")
        click.echo(result.morning.headline)
    else:
        click.echo(f"Relatorio matinal sem analise da IA: {result.morning_error}")
    if result.morning_sent:
        click.echo("Email do relatorio matinal enviado.")


@main.command()
@click.option("--email/--no-email", default=True, show_default=True, help="Envia os emails.")
def tick(email: bool) -> None:
    """Execucao agendada: analisa atividades novas, publica o plano semanal (se auto_publish) e envia o relatorio matinal."""
    _print_tick(run_tick(AppConfig(), email=email), email)


@main.command()
@click.option("--email/--no-email", default=True, show_default=True, help="Envia os emails.")
def daily(email: bool) -> None:
    """Gera o relatorio matinal agora (mesmo que ja tenha sido enviado hoje) e analisa atividades novas."""
    _print_tick(run_tick(AppConfig(), email=email, force_morning=True), email)


@main.command()
@click.option("--limit", default=5, show_default=True, help="Quantidade de atividades recentes a analisar.")
@click.option("--email", is_flag=True, default=False, help="Envia a analise por email.")
def review(limit: int, email: bool) -> None:
    """Analise retrospectiva das ultimas N atividades, como personal trainer. Nunca propoe treinos."""
    config = AppConfig()
    result = run_trainer_review(config, limit=limit, email=email)

    click.echo("=== Resumo ===")
    click.echo(result.summary)
    click.echo()
    click.echo("=== O que evoluiu ===")
    click.echo(result.highlights)
    click.echo()
    click.echo("=== Pontos de atencao ===")
    click.echo(result.improvement_areas)
    click.echo()
    click.echo("=== Recuperacao e peso ===")
    click.echo(result.recovery_assessment)

    if email:
        click.echo()
        click.echo(f"Email de analise enviado para {config.email_to}.")


@main.command()
@click.option("--log-file", type=click.Path(exists=True), required=True, help="Log da execucao que falhou.")
def notify_failure(log_file: str) -> None:
    """Envia um email de alerta quando a execucao agendada falha (no maximo um por dia)."""
    state = load_state()
    today = date.today().isoformat()
    if state.get("last_failure_alert_date") == today:
        click.echo("Alerta de falha ja enviado hoje - nao reenviando.")
        return
    config = AppConfig()
    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
        content = f.read().strip()
    excerpt = content[-2000:] if content else "(log vazio - o script provavelmente falhou antes de gerar qualquer saida)"
    email_report.send_failure_alert(config, excerpt)
    state["last_failure_alert_date"] = today
    save_state(state)


if __name__ == "__main__":
    main()
