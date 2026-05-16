"""CLI commands for Matrix OS evidence backbone contract."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from curaops.evidence import build_operator_report, render_operator_report, summarize_event_stream, validate_event_stream
from curaops.evidence.adapters.agent_evidence_plane import convert_agent_evidence_plane_jsonl
from curaops.evidence.adapters.failure_loop import convert_failure_loop_jsonl
from curaops.evidence.adapters.registry import get_adapter_descriptor, list_adapter_descriptors
from curaops.evidence.adapters.safety_guard import convert_safety_guard_jsonl

console = Console(width=200)
evidence_app = typer.Typer(help="Matrix OS evidence backbone contract utilities")
adapter_app = typer.Typer(help="Evidence adapter registry discovery")
evidence_app.add_typer(adapter_app, name="adapter")


@evidence_app.command("adapters")
def adapters():
    """List registered Matrix OS evidence adapters."""

    table = Table(title="Matrix OS Evidence Adapters")
    table.add_column("Adapter ID")
    table.add_column("Source Project")
    table.add_column("Execution")
    table.add_column("Production Status")
    table.add_column("Events", justify="right")
    for descriptor in list_adapter_descriptors():
        table.add_row(
            descriptor.adapter_id,
            descriptor.source_project,
            descriptor.execution_mode,
            descriptor.production_status,
            str(len(descriptor.supported_event_types)),
        )
    console.print(table)


@adapter_app.command("show")
def show_adapter(
    adapter_id: str = typer.Argument(..., help="Evidence adapter id to inspect"),
):
    """Show one registered evidence adapter descriptor."""

    try:
        descriptor = get_adapter_descriptor(adapter_id)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    table = Table(title=f"Evidence Adapter: {descriptor.adapter_id}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("name", descriptor.name)
    table.add_row("source_project", descriptor.source_project)
    table.add_row("module_path", descriptor.module_path)
    table.add_row("docs_path", descriptor.docs_path)
    table.add_row("input_contract", descriptor.input_contract)
    table.add_row("execution_mode", descriptor.execution_mode)
    table.add_row("production_status", descriptor.production_status)
    table.add_row("external_repo_policy", descriptor.external_repo_policy)
    table.add_row("supported_event_types", "\n".join(descriptor.supported_event_types))
    table.add_row("cli_commands", "\n".join(descriptor.cli_commands))
    console.print(table)


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


@evidence_app.command("convert-agent-plane")
def convert_agent_plane(
    input_events: Path = typer.Argument(..., help="agent-evidence-plane JSONL input stream"),
    output_events: Path = typer.Argument(..., help="Matrix OS JSONL output stream"),
):
    """Convert compatible agent-evidence-plane events into Matrix OS events."""

    try:
        count = convert_agent_evidence_plane_jsonl(input_events, output_events)
    except ValueError as exc:
        console.print(f"[red]Agent evidence plane conversion failed[/red]: {exc}")
        raise typer.Exit(1) from exc
    console.print(f"[green]Converted {count} agent-evidence-plane events[/green] to {output_events}")


@evidence_app.command("convert-safety-guard")
def convert_safety_guard(
    input_results: Path = typer.Argument(..., help="Safety Guard result JSONL input stream"),
    output_events: Path = typer.Argument(..., help="Matrix OS JSONL output stream"),
):
    """Convert compatible Safety Guard results into Matrix OS events."""

    try:
        count = convert_safety_guard_jsonl(input_results, output_events)
    except ValueError as exc:
        console.print(f"[red]Safety Guard conversion failed[/red]: {exc}")
        raise typer.Exit(1) from exc
    console.print(f"[green]Converted {count} Safety Guard results[/green] to {output_events}")


@evidence_app.command("convert-failure-loop")
def convert_failure_loop(
    input_results: Path = typer.Argument(..., help="failure-driven-loop result JSONL input stream"),
    output_events: Path = typer.Argument(..., help="Matrix OS JSONL output stream"),
):
    """Convert compatible failure-driven-loop results into Matrix OS events."""

    try:
        count = convert_failure_loop_jsonl(input_results, output_events)
    except ValueError as exc:
        console.print(f"[red]failure-loop conversion failed[/red]: {exc}")
        raise typer.Exit(1) from exc
    console.print(f"[green]Converted {count} failure-loop events[/green] to {output_events}")


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


@evidence_app.command("report")
def report(
    events: Path = typer.Argument(..., help="Matrix OS EventEnvelope JSONL stream to report on"),
    format: str = typer.Option("text", "--format", help="Report format: text, markdown, or json"),
):
    """Render an operator-readable evidence report without external runtime execution."""

    if format not in {"text", "markdown", "json"}:
        console.print(f"[red]Evidence report failed[/red]: unsupported format: {format}")
        raise typer.Exit(1)
    try:
        operator_report = build_operator_report(events)
        rendered = render_operator_report(operator_report, format=format)  # type: ignore[arg-type]
    except Exception as exc:
        console.print(f"[red]Evidence report failed[/red]: {exc}")
        raise typer.Exit(1) from exc
    console.print(rendered, markup=False, end="")
