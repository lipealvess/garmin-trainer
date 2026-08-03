from __future__ import annotations

import json
import sys
from datetime import date

import click

from . import email_report
from .config import AppConfig, load_profile, save_profile
from .garmin_client import GarminClient
from .pipeline import generate_coach_plan, push_plan, run_pipeline, sync_activities

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


if __name__ == "__main__":
    main()
