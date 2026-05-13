"""CLI commands for Matrix OS evidence backbone contract."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from curaops.evidence import summarize_event_stream, validate_event_stream

console = Console()
evidence_app = typer.Typer(help="Matrix OS evidence backbone contract utilities")


@evidence_app.command("validate")
def validate(
    events: Path = typer.Argument(..., help="JSONL evidence event stream to validate"),
):
    """Validate a Matrix OS evidence event JSONL stream."""

    result = validate_event_stream(events)
    if result["valid"]:
        console.print(f"[green]Evidence stream valid[/green]: {result['events']} events")
        raise typer.Exit(0)
    console.print(f"[red]Evidence stream invalid[/red]: {len(result['errors'])} errors")
    for error in result["errors"]:
        console.print(f"- {error}")
    raise typer.Exit(1)


@evidence_app.command("summarize")
def summarize(
    events: Path = typer.Argument(..., help="JSONL evidence event stream to summarize"),
):
    """Summarize a valid Matrix OS evidence event JSONL stream."""

    validation = validate_event_stream(events)
    if not validation["valid"]:
        console.print(f"[red]Evidence stream invalid[/red]: {len(validation['errors'])} errors")
        for error in validation["errors"]:
            console.print(f"- {error}")
        raise typer.Exit(1)

    summary = summarize_event_stream(events)
    console.print(f"[green]Evidence events:[/green] {summary['events']}")

    table = Table(title="Evidence Event Summary")
    table.add_column("Dimension")
    table.add_column("Value")
    table.add_column("Count", justify="right")
    for dimension in ("event_types", "producers", "subjects"):
        values = summary[dimension]
        for value, count in values.items():
            table.add_row(dimension, value, str(count))
    console.print(table)
