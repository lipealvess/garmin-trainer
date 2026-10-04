from __future__ import annotations

import json
import sys
from datetime import date

import click

from . import email_report
from .config import AppConfig, load_profile, save_profile
from .garmin_client import GarminClient
from .metrics import fmt_pace
from .pipeline import (
    TickResult,
    generate_coach_plan,
    push_plan,
    run_pipeline,
    run_tick,
    run_trainer_review,
    sync_activities,
)
from .state import load_state, save_state

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


@click.group()
def main() -> None:
    """Pipeline de treinos automatizado: Garmin <-> IA (Gemini)."""


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
@click.option("--days-ahead", default=7, show_default=True, help="Horizonte de planejamento em dias.")
@click.option("--push", is_flag=True, default=False, help="Envia e agenda os treinos gerados no Garmin Connect.")
@click.option("--start-date", default=None, help="Data de inicio do plano (YYYY-MM-DD). Padrao: hoje.")
@click.option("--email", is_flag=True, default=False, help="Envia um email com os insights do plano gerado.")
def coach(days_ahead: int, push: bool, start_date: str | None, email: bool) -> None:
    """Gera o proximo bloco de treinos com a IA. Por padrao roda em modo dry-run (nao envia nada ao Garmin)."""
    config = AppConfig()
    profile = load_profile()
    client = GarminClient(config)
    client.login()
    parsed_start = date.fromisoformat(start_date) if start_date else None

    sync_result = sync_activities(client, profile)
    plan = generate_coach_plan(
        config, client, profile, sync_result, days_ahead=days_ahead, start_date=parsed_start
    )

    click.echo("=== Analise ===")
    click.echo(plan.analysis)
    click.echo()
    click.echo("=== O que melhorou ===")
    click.echo(plan.highlights)
    click.echo()
    click.echo("=== Pontos de atencao ===")
    click.echo(plan.improvement_areas)
    click.echo()
    click.echo("=== Recuperacao (sono/estresse/HRV) ===")
    click.echo(plan.recovery_assessment)
    click.echo()
    click.echo("=== Metricas e alvos para os proximos treinos ===")
    click.echo(plan.next_targets)
    click.echo()
    click.echo("=== Treinos planejados ===")
    for workout in plan.planned_workouts:
        click.echo(f"- {workout.date} [{workout.sport}] {workout.name}: {workout.description}")

    if push:
        push_plan(client, profile, plan)
        save_profile(profile)
        click.echo()
        click.echo(f"{len(plan.planned_workouts)} treino(s) enviados e agendados no Garmin Connect.")
    else:
        click.echo()
        click.echo("Modo dry-run: nada foi enviado ao Garmin. Rode novamente com --push para confirmar.")

    if email:
        email_report.send_report(config, plan, sync_result)
        click.echo(f"Email de insights enviado para {config.email_to}.")


@main.command()
@click.option("--days-ahead", default=7, show_default=True, help="Horizonte de planejamento em dias.")
@click.option("--push", is_flag=True, default=False, help="Envia e agenda os treinos gerados no Garmin Connect.")
@click.option("--json-out", type=click.Path(), default=None, help="Salva o plano gerado em um arquivo JSON.")
@click.option("--start-date", default=None, help="Data de inicio do plano (YYYY-MM-DD). Padrao: hoje.")
@click.option("--email", is_flag=True, default=False, help="Envia um email com os insights do plano gerado.")
def run(days_ahead: int, push: bool, json_out: str | None, start_date: str | None, email: bool) -> None:
    """Roda o pipeline completo: sincroniza atividades, chama a IA e (opcionalmente) publica os treinos."""
    config = AppConfig()
    parsed_start = date.fromisoformat(start_date) if start_date else None
    sync_result, plan = run_pipeline(
        config, push=push, days_ahead=days_ahead, start_date=parsed_start, email=email
    )

    click.echo(sync_result.summaries_md)
    click.echo()

    if plan is None:
        click.echo("Nenhuma atividade nova desde a ultima execucao — pipeline nao gerou nem publicou nada.")
        return

    click.echo(plan.analysis)

    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(plan.model_dump(), f, ensure_ascii=False, indent=2)
        click.echo(f"Plano salvo em {json_out}")

    if not push:
        click.echo()
        click.echo("Modo dry-run: nada foi enviado ao Garmin. Rode novamente com --push para confirmar.")

    if email:
        click.echo(f"Email de insights enviado para {config.email_to}.")


def _print_tick(result: TickResult, email: bool) -> None:
    if not result.activities:
        click.echo("Nenhuma atividade nova.")
    for item in result.activities:
        s = item.detail.summary
        click.echo(f"=== Atividade: {s.date} {s.name} ({s.distance_km} km, {fmt_pace(s.avg_pace_min_per_km)}/km) ===")
        click.echo(item.analysis.headline if item.analysis else f"Analise da IA indisponivel: {item.error}")
        if email:
            click.echo("Email da atividade enviado.")

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
    """Execucao agendada: analisa atividades novas e envia o relatorio matinal uma vez por dia. Nunca gera nem publica treinos - o treinador Greg (Garmin Coach) cuida disso."""
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
