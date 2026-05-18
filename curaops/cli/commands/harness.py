"""CLI commands for read-only Matrix OS harness operator workflows."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from curaops.harness.operator_status import build_harness_operator_status, render_harness_operator_status
from curaops.harness.route_plan import OperatorIntent, plan_route, render_route_plan

console = Console(width=200)
harness_app = typer.Typer(help="Read-only Matrix OS harness operator workflow views")


@harness_app.command("status")
def status(
    events: Path | None = typer.Option(
        None,
        "--events",
        help="Matrix OS EventEnvelope JSONL stream; defaults to changes/evidence/events.jsonl",
    ),
) -> None:
    """Show a read-only operator status over evidence, adapters, gateway, and UI metadata."""

    try:
        operator_status = build_harness_operator_status(events)
    except Exception as exc:
        console.print(f"[red]Harness status failed[/red]: {exc}")
        raise typer.Exit(1) from exc
    console.print(render_harness_operator_status(operator_status), markup=False, end="")


@harness_app.command("route-plan")
def route_plan(
    intent: str = typer.Option(
        ...,
        "--intent",
        help="Operator intent to translate into a non-executing dry-run route plan.",
    ),
) -> None:
    """Translate an operator intent into a descriptor-only dry-run route plan."""

    plan = plan_route(OperatorIntent(text=intent))
    console.print(render_route_plan(plan), markup=False, end="")
    if plan.fail_closed:
        raise typer.Exit(2)
