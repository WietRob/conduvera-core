"""Accountable Agent Layer CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

console = Console()

accountable_app = typer.Typer(help="Accountable Agent - AI-assisted change accountability")


@accountable_app.command("preflight")
@accountable_app.command("pre-flight")
def accountable_preflight(
    cr_id: str = typer.Option(..., "--cr", "-c", help="Existing Change Request ID"),
    requirements: str = typer.Option(..., "--requirements", "-r", help="Requirement refs (comma-separated)"),
    change_type: str = typer.Option("feature", "--type", "-t", help="Change type: feature, bugfix, refactor, test"),
    impact_level: Optional[str] = typer.Option(None, "--impact", help="Impact levels (comma-separated: SYS,ARCH,SW,CODE)"),
):
    """Run the Accountable Agent pre-flight gate before AI-assisted work."""
    try:
        from conduvera.skills.accountable_agent import AccountableAgentService

        service = AccountableAgentService(project_root=Path.cwd())
        req_refs = [r.strip() for r in requirements.split(",") if r.strip()]
        impacts = [i.strip() for i in impact_level.split(",") if i.strip()] if impact_level else None
        result = service.pre_flight_check(
            cr_id=cr_id,
            requirement_refs=req_refs,
            change_type=change_type,
            impact_level=impacts,
        )

        if result["passed"]:
            console.print(f"[green]✅ PREFLIGHT PASS[/green] {cr_id}")
            for warning in result.get("warnings", []):
                console.print(f"  ⚠ {warning}")
            return

        console.print(f"[bold red]🚫 PREFLIGHT BLOCK[/bold red] {cr_id}")
        for block in result.get("blocks", []):
            console.print(f"  • {block}")
        for warning in result.get("warnings", []):
            console.print(f"  ⚠ {warning}")
        raise typer.Exit(2)
    except ImportError as exc:
        console.print(f"[red]Error: accountable_agent skill not found: {exc}[/red]")
        raise typer.Exit(1) from exc


@accountable_app.command("register")
def accountable_register(
    agent_id: str = typer.Option(..., "--agent-id", "-a", help="Agent identifier"),
    agent_name: str = typer.Option(..., "--name", "-n", help="Agent name"),
    model: str = typer.Option(..., "--model", "-m", help="AI model used"),
    description: str = typer.Option(..., "--description", "-d", help="Change description"),
    change_type: str = typer.Option("feature", "--type", "-t", help="Change type: feature, bugfix, refactor, test"),
    cr_id: Optional[str] = typer.Option(None, "--cr", "-c", help="Linked Change Request ID"),
    requirements: Optional[str] = typer.Option(None, "--requirements", "-r", help="Requirement refs (comma-separated)"),
    tools: Optional[str] = typer.Option(None, "--tools", help="Tools used (comma-separated)"),
    files: Optional[str] = typer.Option(None, "--files", "-f", help="Files affected (comma-separated)"),
    strict: bool = typer.Option(True, "--strict/--no-strict", help="Block if mandatory links missing"),
):
    """Register an accountable AI-assisted change."""
    try:
        from conduvera.skills.accountable_agent import (
            AccountableAgentService,
            AccountabilityError,
            AgentContext,
            ChangeIntent,
            MissingMandatoryLinkError,
        )

        service = AccountableAgentService(project_root=Path.cwd())
        agent_context = AgentContext(
            agent_id=agent_id,
            agent_name=agent_name,
            model=model,
            tools_used=[t.strip() for t in tools.split(",") if t.strip()] if tools else [],
        )
        change_intent = ChangeIntent(
            description=description,
            change_type=change_type,
            files_affected=[f.strip() for f in files.split(",") if f.strip()] if files else [],
        )
        req_refs = [r.strip() for r in requirements.split(",") if r.strip()] if requirements else None

        ac = service.register_accountable_change(
            agent_context=agent_context,
            change_intent=change_intent,
            cr_id=cr_id,
            requirement_refs=req_refs,
            strict=strict,
        )
        console.print(f"[green]✅ Accountable change registered:[/green] {ac.accountable_id}")
        console.print(f"  Status: {ac.status}")
        if ac.cr_id:
            console.print(f"  Linked CR: {ac.cr_id}")
        if ac.requirement_refs:
            console.print(f"  Requirements: {', '.join(ac.requirement_refs)}")
    except MissingMandatoryLinkError as exc:
        console.print(f"[bold red]🚫 BLOCKED[/bold red] {exc}")
        raise typer.Exit(1) from exc
    except AccountabilityError as exc:
        console.print(f"[bold red]🚫 BLOCKED[/bold red] {exc}")
        raise typer.Exit(2) from exc
    except ImportError as exc:
        console.print(f"[red]Error: accountable_agent skill not found: {exc}[/red]")
        raise typer.Exit(1) from exc


@accountable_app.command("validate")
def accountable_validate(
    accountable_id: str = typer.Argument(..., help="Accountable change ID"),
):
    """Validate an accountable change has all required links."""
    try:
        from conduvera.skills.accountable_agent import AccountableAgentService, AccountabilityError

        service = AccountableAgentService(project_root=Path.cwd())
        result = service.validate_accountability(accountable_id)

        if result["valid"]:
            console.print(f"[green]✅ VALID[/green] {accountable_id}")
            console.print(f"  CR: {result.get('cr_id', 'N/A')}")
            console.print(f"  Requirements: {', '.join(result.get('requirement_refs', []))}")
            return

        console.print(f"[bold red]❌ INVALID[/bold red] {accountable_id}")
        for issue in result.get("issues", []):
            console.print(f"  • {issue}")
        if result.get("error"):
            console.print(f"  • {result['error']}")
        raise typer.Exit(1)
    except AccountabilityError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(2) from exc
    except ImportError as exc:
        console.print(f"[red]Error: accountable_agent skill not found: {exc}[/red]")
        raise typer.Exit(1) from exc


@accountable_app.command("evidence")
def accountable_evidence(
    accountable_id: str = typer.Argument(..., help="Accountable change ID"),
    format: str = typer.Option("json", "--format", "-f", help="Output format: json, markdown"),
):
    """Generate evidence report for an accountable change."""
    try:
        from conduvera.skills.accountable_agent import AccountableAgentService, AccountabilityError

        service = AccountableAgentService(project_root=Path.cwd())
        evidence_path = service.generate_accountability_evidence(accountable_id, format)
        console.print(f"[green]✅ Evidence generated:[/green] {evidence_path}")

        if format == "json":
            with open(evidence_path, encoding="utf-8") as handle:
                evidence = json.load(handle)
            ac = evidence.get("accountable_change", {})
            console.print("\n[bold]Accountability Summary:[/bold]")
            console.print(f"  Agent: {ac.get('agent_context', {}).get('agent_name', 'N/A')}")
            console.print(f"  Model: {ac.get('agent_context', {}).get('model', 'N/A')}")
            console.print(f"  Change: {ac.get('change_intent', {}).get('description', 'N/A')[:50]}...")
            console.print(f"  Status: {ac.get('status', 'N/A')}")
            console.print(f"  Valid: {'✅' if evidence.get('validation', {}).get('valid') else '❌'}")
    except AccountabilityError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(2) from exc
    except ImportError as exc:
        console.print(f"[red]Error: accountable_agent skill not found: {exc}[/red]")
        raise typer.Exit(1) from exc
