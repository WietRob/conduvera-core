"""CLI commands for read-only Matrix OS harness operator workflows."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from curaops.harness.operator_status import build_harness_operator_status, render_harness_operator_status
from curaops.harness.route_plan import OperatorIntent, plan_route, render_route_plan, route_plan_to_dict
from curaops.harness.route_plan_viewer import build_route_plan_view, render_route_plan_view

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
    output_format: str = typer.Option(
        "text",
        "--format",
        help="Output format: text or json.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Optional path to write the route plan output. Parent directories are created if needed.",
    ),
) -> None:
    """Translate an operator intent into a descriptor-only dry-run route plan."""

    plan = plan_route(OperatorIntent(text=intent))
    normalized_format = output_format.lower()
    if normalized_format == "json":
        rendered = json.dumps(route_plan_to_dict(plan), indent=2, sort_keys=True) + "\n"
    elif normalized_format == "text":
        rendered = render_route_plan(plan)
    else:
        console.print(f"[red]Unsupported route-plan format[/red]: {output_format}")
        raise typer.Exit(1)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        console.print(f"Wrote dry-run route plan: {output}", markup=False)
    else:
        console.print(rendered, markup=False, end="")

    if plan.fail_closed:
        raise typer.Exit(2)


@harness_app.command("route-plan-view")
def route_plan_view(
    input_path: Path = typer.Option(
        ...,
        "--input",
        help="Existing route-plan.v1 JSON file to render as a display-only Matrix UI handoff view.",
    ),
) -> None:
    """Render a read-only Matrix UI route-plan viewer stub from existing JSON."""

    try:
        view = build_route_plan_view(input_path)
    except Exception as exc:
        console.print(f"[red]route-plan-view failed[/red]: {exc}")
        raise typer.Exit(1) from exc

    console.print(render_route_plan_view(view), markup=False, end="")
