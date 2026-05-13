"""CLI commands for Matrix OS UI/MCP/editor scaffolding."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from curaops.harness.scaffolding import get_scaffolding_slice, list_scaffolding_slices

console = Console()
scaffold_app = typer.Typer(
    help="Matrix OS harness scaffolding - UI/MCP/editor boundaries",
    no_args_is_help=True,
)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


@scaffold_app.command("status")
def status() -> None:
    """Show scaffolding status without launching runtime services."""

    table = Table(title="Matrix OS Scaffolding Status")
    table.add_column("Slice")
    table.add_column("Status")
    table.add_column("Owner")
    table.add_column("Entry points")

    for item in list_scaffolding_slices():
        table.add_row(item.name, item.status, item.owner, "\n".join(item.entrypoints))

    console.print(table)
    console.print(
        "[dim]Scaffolding only: this command does not start UI, MCP, editor, "
        "Safety Guard, evidence-plane, CAS, failure-loop, peekxd, OpenCode, or ai-router runtimes.[/]"
    )


@scaffold_app.command("show")
def show(
    slice_key: str = typer.Argument(..., help="Scaffolding slice: ui, mcp, or editor"),
) -> None:
    """Show one scaffolding slice and verify declared source paths."""

    try:
        item = get_scaffolding_slice(slice_key)
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from exc

    console.print(f"[bold green]{item.name}[/]")
    console.print(f"Status: {item.status}")
    console.print(f"Owner: {item.owner}")

    console.print("\n[bold]Entry points[/]")
    for entrypoint in item.entrypoints:
        console.print(f"- {entrypoint}")

    console.print("\n[bold]Source paths[/]")
    for source_path in item.source_paths:
        marker = "OK" if (PROJECT_ROOT / source_path).exists() else "MISSING"
        console.print(f"- [{marker}] {source_path}")

    console.print("\n[bold]Responsibilities[/]")
    for responsibility in item.responsibilities:
        console.print(f"- {responsibility}")

    console.print("\n[bold]Excluded scope[/]")
    for excluded in item.excluded_scope:
        console.print(f"- {excluded}")
