"""ASPICE support utility CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

console = Console()
aspice_app = typer.Typer(help="ASPICE support utilities - traceability checks")


@aspice_app.command("check")
def aspice_check(
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="Project root to scan"),
) -> None:
    """Check ASPICE traceability conflicts."""
    from conduvera.skills.aspice_conflict_detector import ConflictDetector

    detector = ConflictDetector(root_dir=path)
    conflicts = detector.detect_conflicts()
    report = detector.generate_conflict_report(conflicts)

    console.print(f"ASPICE conflicts: {report['total_conflicts']}")
    for conflict in report["conflicts"]:
        console.print(
            f"- {conflict['severity']} {conflict['type']} "
            f"{conflict['location']}: {conflict['message']}"
        )
    if conflicts:
        raise typer.Exit(1)


@aspice_app.command("link")
def aspice_link(
    requirement: str = typer.Option(..., "--requirement", "-r", help="Requirement ID"),
    file: Path = typer.Option(..., "--file", "-f", help="Implementation or traceability file"),
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="Project root"),
) -> None:
    """Link a requirement document to an implementation file."""
    from conduvera.skills.aspice_link_manager import ASPICELinkManager

    manager = ASPICELinkManager(root_dir=path)
    req_file = manager.find_document(requirement)
    if req_file is None:
        console.print(f"[red]Requirement not found:[/red] {requirement}")
        raise typer.Exit(2)

    changed = manager._add_backlink(req_file, str(file), "implemented_in")
    if changed:
        console.print(f"✅ Linked {requirement} -> {file}")
    else:
        console.print(f"ℹ️ Link already present or not updateable: {requirement} -> {file}")


@aspice_app.command("update-all")
def aspice_update_all(
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="Project root"),
) -> None:
    """Update bidirectional traceability links for all Markdown documents."""
    from conduvera.skills.aspice_link_manager import ASPICELinkManager

    manager = ASPICELinkManager(root_dir=path)
    total_updated = 0
    errors: list[str] = []
    for search_dir in manager.search_dirs:
        if not search_dir.exists():
            continue
        for md_file in search_dir.rglob("*.md"):
            result = manager.update_bidirectional_links(md_file)
            total_updated += result.updated_count
            errors.extend(result.errors)

    console.print(f"ASPICE bidirectional links updated: {total_updated}")
    if errors:
        for error in errors:
            console.print(f"[yellow]- {error}[/yellow]")
        raise typer.Exit(1)
