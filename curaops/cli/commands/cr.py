"""
C CLI — Compliance Change Control commands.

Source: COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md §G
Commands: create, submit, approve, reject, status, list, evidence, validate
           + verification create, verification list, verification validate-type
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

console = Console()

cr_app = typer.Typer(help="Compliance Change Control — CR-driven workflow")
verification_app = typer.Typer(help="VerificationCase management")

# Register verification as subcommand of cr
cr_app.add_typer(verification_app, name="verification")


# ═══════════════════════════════════════════════════════════════
# CR COMMANDS
# ═══════════════════════════════════════════════════════════════


@cr_app.command("create")
def cr_create(
    title: str = typer.Option(..., "--title", "-t", help="CR title (10-80 chars)"),
    problem: str = typer.Option("", "--problem", "-p", help="Problem description"),
    justification: str = typer.Option("", "--justification", "-j", help="Why needed"),
    change_type: str = typer.Option("feature", "--change-type", help="feature|bugfix|refactor|test|docs"),
    linkage_type: Optional[str] = typer.Option(None, "--requirement-linkage-type", help="existing_ref|updated_ref|new_ref"),
    impact_level: Optional[str] = typer.Option(None, "--impact-level", help="Comma-separated: SYS,ARCH,SW,CODE"),
    requirement_refs: Optional[str] = typer.Option(None, "--requirement-refs", "-r", help="Comma-separated req IDs"),
    safety_impact: str = typer.Option("none", "--safety-impact", help="none|low|medium|high"),
    emergency: bool = typer.Option(False, "--emergency", help="Create as EMERGENCY CR"),
    incident_id: Optional[str] = typer.Option(None, "--incident-id", help="Incident ID (emergency)"),
    severity: Optional[str] = typer.Option(None, "--severity", help="P0/P1/P2 (emergency)"),
    rollback_plan: Optional[str] = typer.Option(None, "--rollback-plan", help="Rollback plan (emergency)"),
    post_mortem_date: Optional[str] = typer.Option(None, "--post-mortem-date", help="Post-mortem date, ISO-8601 (emergency)"),
    requester: str = typer.Option("cli-user", "--requester", help="Requester identifier"),
):
    """Create a new Change Request in DRAFT (or EMERGENCY) state."""
    from curaops.skills.change_request import ChangeRequestService

    svc = _get_service()
    impact_list = [il.strip() for il in impact_level.split(",")] if impact_level else []
    refs_list = [r.strip() for r in requirement_refs.split(",")] if requirement_refs else []

    try:
        cr = svc.create_cr(
            title=title,
            requester=requester,
            problem=problem,
            justification=justification,
            change_type=change_type,
            requirement_linkage_type=linkage_type,
            impact_level=impact_list,
            requirement_refs=refs_list,
            safety_impact=safety_impact,
            is_emergency=emergency,
            incident_id=incident_id,
            severity=severity,
            rollback_plan=rollback_plan,
            post_mortem_date=_parse_datetime(post_mortem_date) if post_mortem_date else None,
        )
        console.print(f"[green]✅ Created {cr.id}[/green]")
        console.print(f"  Title:  {cr.title}")
        console.print(f"  Status: {cr.status.value}")
        console.print(f"  Type:   {cr.change_type.value}")
        if refs_list:
            console.print(f"  Refs:   {', '.join(refs_list)}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(2)


@cr_app.command("submit")
def cr_submit(
    cr_id: str = typer.Argument(..., help="CR ID to submit"),
    post_mortem_date: Optional[str] = typer.Option(None, "--post-mortem-date", help="Post-mortem date, ISO-8601 (emergency)"),
    rollback_plan: Optional[str] = typer.Option(None, "--rollback-plan", help="Rollback plan (emergency)"),
):
    """Transition DRAFT/EMERGENCY → SUBMITTED."""
    from curaops.skills.change_request import ChangeRequestService

    svc = _get_service()
    try:
        cr = svc.submit_cr(
            cr_id,
            post_mortem_date=_parse_datetime(post_mortem_date) if post_mortem_date else None,
            rollback_plan=rollback_plan,
        )
        console.print(f"[green]✅ {cr.id} → {cr.status.value.upper()}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(_exit_code(e))


@cr_app.command("approve")
def cr_approve(
    cr_id: str = typer.Argument(..., help="CR ID to approve"),
    reviewer: str = typer.Option(..., "--reviewer", help="Approver identifier"),
    comment: Optional[str] = typer.Option(None, "--comment", help="Approval comment"),
):
    """Transition SUBMITTED → APPROVED."""
    from curaops.skills.change_request import ChangeRequestService

    svc = _get_service()
    try:
        cr = svc.approve_cr(cr_id, reviewer=reviewer, comment=comment or "")
        console.print(f"[green]✅ {cr.id} APPROVED[/green] by {reviewer}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(_exit_code(e))


@cr_app.command("reject")
def cr_reject(
    cr_id: str = typer.Argument(..., help="CR ID to reject"),
    reason: str = typer.Option(..., "--reason", help="Rejection reason"),
):
    """Reject a CR (transition to REJECTED)."""
    from curaops.skills.change_request import ChangeRequestService

    svc = _get_service()
    try:
        cr = svc.reject_cr(cr_id, reason=reason)
        console.print(f"[yellow]❌ {cr.id} REJECTED[/yellow]: {reason}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(_exit_code(e))


@cr_app.command("start")
def cr_start(
    cr_id: str = typer.Argument(..., help="CR ID to start"),
):
    """Transition APPROVED → IN_PROGRESS."""
    _transition(cr_id, "in_progress")


@cr_app.command("complete")
def cr_complete(
    cr_id: str = typer.Argument(..., help="CR ID to complete"),
    files: Optional[str] = typer.Option(None, "--files", "-f", help="Comma-separated affected files"),
    verifications: Optional[str] = typer.Option(None, "--verifications", help="Comma-separated TC-IDs"),
    commits: Optional[str] = typer.Option(None, "--commits", help="Comma-separated commit SHAs"),
):
    """Transition IN_PROGRESS → IMPLEMENTED."""
    from curaops.skills.change_request import ChangeRequestService

    svc = _get_service()
    try:
        cr = svc.complete_cr(
            cr_id,
            affected_files=[f.strip() for f in files.split(",")] if files else None,
            affected_verifications=[v.strip() for v in verifications.split(",")] if verifications else None,
            commits=[c.strip() for c in commits.split(",")] if commits else None,
        )
        console.print(f"[green]✅ {cr.id} IMPLEMENTED[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(_exit_code(e))


@cr_app.command("verify")
def cr_verify(
    cr_id: str = typer.Argument(..., help="CR ID to verify"),
):
    """Transition IMPLEMENTED → VERIFIED (generates evidence first)."""
    from curaops.skills.change_request import ChangeRequestService

    svc = _get_service()
    try:
        svc.generate_evidence(cr_id)
        cr = svc.verify_cr(cr_id)
        console.print(f"[green]✅ {cr.id} VERIFIED[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(_exit_code(e))


@cr_app.command("close")
def cr_close(
    cr_id: str = typer.Argument(..., help="CR ID to close"),
    root_cause_category: Optional[str] = typer.Option(None, "--root-cause-category", help="Bugfix root cause: impl_bug|req_ambiguous|req_missing|arch_bug|sys_bug"),
):
    """Transition VERIFIED → CLOSED."""
    from curaops.skills.change_request import ChangeRequestService

    svc = _get_service()
    try:
        cr = svc.close_cr(cr_id, root_cause_category=root_cause_category)
        console.print(f"[green]✅ {cr.id} → {cr.status.value.upper()}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(_exit_code(e))


@cr_app.command("revise")
def cr_revise(
    cr_id: str = typer.Argument(..., help="CR ID to revise"),
):
    """Transition REJECTED → DRAFT."""
    _transition(cr_id, "draft")


@cr_app.command("status")
def cr_status(
    cr_id: str = typer.Argument(..., help="CR ID"),
):
    """Show CR status and details."""
    from curaops.skills.change_request import ChangeRequestService

    svc = _get_service()
    try:
        cr = svc.get_cr(cr_id)
        console.print(f"[bold]{cr.id}: {cr.title}[/bold]")
        console.print(f"  Status:    {cr.status.value}")
        console.print(f"  Type:      {cr.change_type.value}")
        console.print(f"  Requester: {cr.requester}")
        console.print(f"  Created:   {cr.created.isoformat()}")
        if cr.reviewer:
            console.print(f"  Reviewer:  {cr.reviewer}")
        if cr.requirement_refs:
            console.print(f"  Refs:      {', '.join(cr.requirement_refs)}")
        if cr.affected_verifications:
            console.print(f"  VCs:       {', '.join(cr.affected_verifications)}")
        if cr.rejection_reason:
            console.print(f"  Reason:    {cr.rejection_reason}")
    except FileNotFoundError:
        console.print(f"[red]CR not found: {cr_id}[/red]")
        raise typer.Exit(5)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@cr_app.command("list")
def cr_list(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
):
    """List all Change Requests."""
    from curaops.skills.change_request import ChangeRequestService

    svc = _get_service()
    crs = svc.list_crs(status=status)

    if not crs:
        console.print("[yellow]No Change Requests found[/yellow]")
        return

    table = Table(title="Change Requests")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Type", style="blue")
    table.add_column("Safety", style="red")

    for cr in crs:
        table.add_row(
            cr.id, cr.title[:40], cr.status.value,
            cr.change_type.value, cr.safety_impact.value,
        )
    console.print(table)


@cr_app.command("evidence")
def cr_evidence(
    cr_id: str = typer.Argument(..., help="CR ID to generate evidence for"),
):
    """Generate CCC-1.1.0 evidence for a CR."""
    from curaops.skills.change_request import ChangeRequestService

    svc = _get_service()
    try:
        path = svc.generate_evidence(cr_id)
        console.print(f"[green]✅ Evidence generated:[/green] {path}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(2)


@cr_app.command("validate")
def cr_validate(
    cr_id: str = typer.Argument(..., help="CR ID to validate"),
):
    """Validate CR against all C rules (returns issues)."""
    from curaops.skills.change_request import ChangeRequestService

    svc = _get_service()
    try:
        issues = svc.validate_cr(cr_id)
        blocking = [i for i in issues if i["severity"] == "BLOCKING"]
        warnings = [i for i in issues if i["severity"] == "WARNING"]

        if not issues:
            console.print(f"[green]✅ {cr_id}: All validations passed[/green]")
        else:
            if blocking:
                console.print(f"[bold red]🚫 {cr_id}: {len(blocking)} BLOCKING issues[/bold red]")
                for i in blocking:
                    console.print(f"  • {i['message']}")
                    if i.get("rule"):
                        console.print(f"    Rule: {i['rule']}")
            if warnings:
                console.print(f"[yellow]⚠️  {cr_id}: {len(warnings)} warnings[/yellow]")
                for i in warnings:
                    console.print(f"  • {i['message']}")

            if blocking:
                raise typer.Exit(2)
    except FileNotFoundError:
        console.print(f"[red]CR not found: {cr_id}[/red]")
        raise typer.Exit(5)


# ═══════════════════════════════════════════════════════════════
# VERIFICATION COMMANDS
# ═══════════════════════════════════════════════════════════════


@verification_app.command("create")
def verification_create(
    title: str = typer.Option(..., "--title", "-t", help="Verification title"),
    type_str: str = typer.Option(..., "--type", help="unit|software_integration|software_verification|system_integration|system_verification"),
    validates: str = typer.Option(..., "--validates", help="Comma-separated requirement IDs"),
    implemented_in: str = typer.Option(..., "--implemented-in", help="Test file path"),
    component: str = typer.Option(..., "--component", help="Module under test"),
    owner: str = typer.Option("cli-user", "--owner", help="Owner"),
    description: str = typer.Option("", "--description", "-d", help="Description"),
):
    """Create a new VerificationCase."""
    from curaops.skills.change_request import VerificationService

    svc = _get_verification_service()
    try:
        vc = svc.create_verification(
            title=title,
            type_str=type_str,
            validates=[v.strip() for v in validates.split(",")],
            implemented_in=implemented_in,
            component=component,
            owner=owner,
            description=description,
        )
        console.print(f"[green]✅ Created {vc.id}[/green]")
        console.print(f"  Title:      {vc.title}")
        console.print(f"  Type:       {vc.type.value}")
        console.print(f"  Validates:  {', '.join(vc.validates)}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(2)


@verification_app.command("list")
def verification_list(
    validates: Optional[str] = typer.Option(None, "--validates", help="Filter by requirement ID"),
):
    """List VerificationCases."""
    from curaops.skills.change_request import VerificationService

    svc = _get_verification_service()
    vcs = svc.list_verifications(validates=validates)

    if not vcs:
        console.print("[yellow]No VerificationCases found[/yellow]")
        return

    table = Table(title="VerificationCases")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("Type", style="blue")
    table.add_column("Status", style="yellow")
    table.add_column("Validates", style="magenta")

    for vc in vcs:
        table.add_row(
            vc.id, vc.title[:30], vc.type.value,
            vc.status.value, ", ".join(vc.validates),
        )
    console.print(table)


@verification_app.command("validate-type")
def verification_validate_type(
    tc_id: str = typer.Argument(..., help="VerificationCase ID"),
    req_id: str = typer.Argument(..., help="Requirement ID to check against"),
):
    """Check that VerificationCase type matches requirement level."""
    from curaops.skills.change_request import VerificationService

    svc = _get_verification_service()
    try:
        valid = svc.validate_verification_type(tc_id, req_id)
        if valid:
            console.print(f"[green]✅ Type mapping valid: {tc_id} ↔ {req_id}[/green]")
        else:
            console.print(f"[red]❌ Type mismatch: {tc_id} does not match {req_id}[/red]")
            raise typer.Exit(2)
    except FileNotFoundError:
        console.print(f"[red]VerificationCase not found: {tc_id}[/red]")
        raise typer.Exit(5)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


def _get_service():
    from curaops.skills.change_request import ChangeRequestService
    return ChangeRequestService(
        changes_dir=Path.cwd() / "changes",
        evidence_dir=Path.cwd() / "changes" / "evidence",
    )


def _get_verification_service():
    from curaops.skills.change_request import VerificationService
    return VerificationService(verification_dir=Path.cwd() / "verification")


def _parse_datetime(value: str) -> datetime:
    """Parse an ISO-8601 datetime string, accepting trailing Z for UTC."""
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _transition(cr_id: str, target: str):
    """Generic transition helper."""
    from curaops.skills.change_request import ChangeRequestService

    svc = _get_service()
    try:
        cr = svc.transition_cr(cr_id, target)
        console.print(f"[green]✅ {cr.id} → {cr.status.value.upper()}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(_exit_code(e))


def _exit_code(exc: Exception) -> int:
    """Map exceptions to C-IMPLEMENTATION_CONTRACT §G.3 exit codes."""
    from curaops.skills.change_request import InvalidTransitionError, MissingFieldsError
    if isinstance(exc, InvalidTransitionError):
        return 3
    if isinstance(exc, MissingFieldsError):
        return 4
    if isinstance(exc, FileNotFoundError):
        return 5
    return 2
