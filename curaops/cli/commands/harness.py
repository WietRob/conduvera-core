"""CLI commands for read-only Matrix OS harness operator workflows."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from curaops.harness.operator_status import build_harness_operator_status, render_harness_operator_status

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
