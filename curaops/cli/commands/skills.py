"""
CuraOps Skills CLI Commands

Integrates 7 extracted skills into CuraOps CLI:
- safety-guard (P1-Critical)
- change-request (P1)
- aspice-link-manager (P2)
- pattern-learning (P2)
- session-manager (P2)
- aspice-conflict-detector (P2)
- multi-agent-lock (P2)

Usage:
    curaops safety check --delete file.txt
    curaops cr create --title "Fix bug"
    curaops session start --project ~/myproject
    curaops aspice check
    curaops lock claim --file src/main.py --agent cursor
"""

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

# Skills are now symlinks in src/ directory
# Import paths: src.safety_guard, src.change_request, etc.

console = Console()

# Create sub-command apps
safety_app = typer.Typer(help="Safety Guard - Protect production data")
cr_app = typer.Typer(help="Change Request - CR-driven workflow")
session_app = typer.Typer(help="Session Manager - Session lifecycle")
aspice_app = typer.Typer(help="ASPICE Compliance - Link management & validation")
lock_app = typer.Typer(help="Multi-Agent Lock - Coordinate file access")
pattern_app = typer.Typer(help="Pattern Learning - Learn from behavior")


# ═══════════════════════════════════════════════════════════════
# SAFETY GUARD COMMANDS
# ═══════════════════════════════════════════════════════════════

@safety_app.command("check")
def safety_check(
    path: str = typer.Argument(..., help="Path to check"),
    operation: str = typer.Option("delete", "--operation", "-o", help="Operation: delete, modify, execute"),
):
    """Check if an operation is safe on a path."""
    try:
        from curaops.skills.safety_guard import SafetyGuard
        
        sg = SafetyGuard()
        try:
            validated_path = sg.validate_path(path, operation)
            console.print(f"[green]✅ SAFE[/green] {path}")
        except Exception as e:
            console.print(f"[bold red]🚫 BLOCKED[/bold red] {e}")
            raise typer.Exit(1)
            
    except ImportError:
        console.print("[red]Error: safety_guard skill not found[/red]")
        raise typer.Exit(1)


@safety_app.command("validate-delete")
def safety_validate_delete(
    path: str = typer.Argument(..., help="Path to validate for deletion"),
):
    """Validate if path can be safely deleted."""
    safety_check(path, operation="delete", block=True)


# ═══════════════════════════════════════════════════════════════
# CHANGE REQUEST COMMANDS
# ═══════════════════════════════════════════════════════════════

@cr_app.command("create")
def cr_create(
    title: str = typer.Option(..., "--title", "-t", help="CR title"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="CR description"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Files/paths scope (comma-separated)"),
    priority: str = typer.Option("MEDIUM", "--priority", "-p", help="Priority: LOW, MEDIUM, HIGH, CRITICAL"),
):
    """Create a new Change Request."""
    try:
        from curaops.skills.change_request import ChangeRequestService
        
        cr_service = ChangeRequestService(changes_path=Path.cwd() / "changes")
        result = cr_service.submit_change_request(
            title=title,
            description=description or ""
        )
        
        cr_id = result.get("id", "unknown")
        console.print(f"[green]✅ Created CR:[/green] {cr_id}")
        console.print(f"  Title: {title}")
        console.print(f"  File: {result.get('file', 'N/A')}")
        
    except ImportError:
        console.print("[red]Error: change_request skill not found[/red]")
        raise typer.Exit(1)


@cr_app.command("list")
def cr_list(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
):
    """List Change Requests."""
    try:
        from curaops.skills.change_request import ChangeRequest
        
        crs = ChangeRequest.list_all(status=status, limit=limit)
        
        table = Table(title="Change Requests")
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="green")
        table.add_column("Status", style="yellow")
        table.add_column("Priority", style="red")
        
        for cr in crs:
            table.add_row(cr.cr_id, cr.title, cr.status, cr.priority)
        
        console.print(table)
        
    except ImportError:
        console.print("[red]Error: change_request skill not found[/red]")
        raise typer.Exit(1)


@cr_app.command("show")
def cr_show(
    cr_id: str = typer.Argument(..., help="CR ID to show"),
):
    """Show Change Request details."""
    try:
        from curaops.skills.change_request import ChangeRequest
        
        cr = ChangeRequest.load(cr_id)
        
        console.print(f"[bold]Change Request: {cr.cr_id}[/bold]")
        console.print(f"  Title: {cr.title}")
        console.print(f"  Status: {cr.status}")
        console.print(f"  Priority: {cr.priority}")
        console.print(f"  Created: {cr.created_at}")
        if cr.scope:
            console.print(f"  Scope: {', '.join(cr.scope)}")
        if cr.blockers:
            console.print(f"[red]  Blockers: {len(cr.blockers)}[/red]")
            
    except ImportError:
        console.print("[red]Error: change_request skill not found[/red]")
        raise typer.Exit(1)


# ═══════════════════════════════════════════════════════════════
# SESSION MANAGER COMMANDS
# ═══════════════════════════════════════════════════════════════

@session_app.command("start")
def session_start(
    agent: str = typer.Option("cli", "--agent", "-a", help="Agent name (cursor, claude, etc.)"),
    model: str = typer.Option("default", "--model", "-m", help="Model name"),
    prompt: str = typer.Option("CLI session", "--prompt", "-p", help="Session prompt/task"),
):
    """Start a new session."""
    try:
        from curaops.skills.session_manager import AgentSessionManager
        
        sm = AgentSessionManager(storage_dir=Path.home() / ".curaops" / "sessions")
        session = sm.create_session(agent=agent, model=model, prompt=prompt)
        
        console.print(f"[green]✅ Session started:[/green] {session.session_id}")
        console.print(f"  Agent: {session.agent}")
        console.print(f"  Model: {session.model}")
        console.print(f"  Status: {session.status}")
        
    except ImportError:
        console.print("[red]Error: session_manager skill not found[/red]")
        raise typer.Exit(1)


@session_app.command("status")
def session_status():
    """Show current session status."""
    try:
        from curaops.skills.session_manager import AgentSessionManager
        
        sm = AgentSessionManager(storage_dir=Path.home() / ".curaops" / "sessions")
        sessions = sm.list_sessions()
        
        active = [s for s in sessions if s.status == "active"]
        
        if active:
            session = active[0]
            console.print(f"[bold]Active Session:[/bold] {session.session_id}")
            console.print(f"  Agent: {session.agent}")
            console.print(f"  Model: {session.model}")
            console.print(f"  Status: {session.status}")
            console.print(f"  Created: {session.created_at}")
        else:
            console.print(f"[yellow]No active session[/yellow] (Total: {len(sessions)} sessions)")
            
    except ImportError:
        console.print("[red]Error: session_manager skill not found[/red]")
        raise typer.Exit(1)


@session_app.command("end")
def session_end(
    session_id: str = typer.Argument(..., help="Session ID to end"),
):
    """End a session."""
    try:
        from curaops.skills.session_manager import AgentSessionManager
        
        sm = AgentSessionManager(storage_dir=Path.home() / ".curaops" / "sessions")
        session = sm.get_session(session_id)
        
        if session:
            session.status = "completed"
            sm.save_session(session)
            console.print(f"[green]✅ Session ended:[/green] {session_id}")
        else:
            console.print(f"[yellow]Session not found:[/yellow] {session_id}")
            
    except ImportError:
        console.print("[red]Error: session_manager skill not found[/red]")
        raise typer.Exit(1)


@session_app.command("list")
def session_list(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status (active, completed, error)"),
):
    """List all sessions."""
    try:
        from curaops.skills.session_manager import AgentSessionManager
        
        sm = AgentSessionManager(storage_dir=Path.home() / ".curaops" / "sessions")
        sessions = sm.list_sessions()
        
        if status:
            sessions = [s for s in sessions if s.status == status]
        
        table = Table(title=f"Sessions ({len(sessions)} total)")
        table.add_column("ID", style="cyan")
        table.add_column("Agent", style="green")
        table.add_column("Model", style="blue")
        table.add_column("Status", style="yellow")
        
        for session in sessions:
            table.add_row(
                session.session_id[:20] + "...",
                session.agent,
                session.model,
                session.status
            )
        
        console.print(table)
        
    except ImportError:
        console.print("[red]Error: session_manager skill not found[/red]")
        raise typer.Exit(1)


# ═══════════════════════════════════════════════════════════════
# ASPICE COMMANDS
# ═══════════════════════════════════════════════════════════════

@aspice_app.command("link")
def aspice_link(
    requirement: str = typer.Option(..., "--req", "-r", help="Requirement ID (e.g., SW-REQ-001)"),
    file: Path = typer.Option(..., "--file", "-f", help="File to link"),
    bidirectional: bool = typer.Option(True, "--bidirectional/--no-bidirectional", help="Update bidirectional links"),
):
    """Create ASPICE traceability link (requirement → implementation)."""
    try:
        from curaops.skills.aspice_link_manager import ASPICELinkManager
        
        lm = ASPICELinkManager(root_dir=Path.cwd())
        
        # Parse the requirement file
        req_file = Path.cwd() / "requirements" / "software" / f"{requirement}.md"
        if not req_file.exists():
            req_file = Path.cwd() / "requirements" / f"{requirement}.md"
        
        if req_file.exists():
            req = lm.parse_document(req_file)
            if req:
                # Add implementation link
                if str(file) not in req.implemented_in:
                    req.implemented_in.append(str(file))
                    console.print(f"[green]✅ Linked:[/green] {requirement} → {file}")
                else:
                    console.print(f"[yellow]⚠️  Already linked:[/yellow] {requirement} → {file}")
                
                # Update bidirectional links
                if bidirectional:
                    with console.status("[bold green]Updating bidirectional links..."):
                        result = lm.update_bidirectional_links(req_file)
                    if result.success:
                        console.print(f"[green]✅ Updated {result.updated_count} bidirectional links[/green]")
                    else:
                        console.print(f"[yellow]⚠️  Updated {result.updated_count} links with {len(result.errors)} errors[/yellow]")
                        for error in result.errors[:3]:  # Show first 3 errors
                            console.print(f"  [dim]- {error}[/dim]")
            else:
                console.print(f"[red]Error: Could not parse {req_file}[/red]")
        else:
            console.print(f"[yellow]⚠️  Requirement file not found: {req_file}[/yellow]")
            console.print(f"  Searched in: requirements/software/ and requirements/")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@aspice_app.command("update-all")
def aspice_update_all(
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="Project root path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be updated without making changes"),
):
    """Update bidirectional links for all documents (<5min SLA)."""
    try:
        from curaops.skills.aspice_link_manager import ASPICELinkManager
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        
        lm = ASPICELinkManager(root_dir=path)
        
        # Collect all documents
        all_docs = []
        for search_dir in lm.search_dirs:
            if not search_dir.exists():
                continue
            for md_file in search_dir.rglob("*.md"):
                all_docs.append(md_file)
        
        if not all_docs:
            console.print("[yellow]No requirement documents found[/yellow]")
            return
        
        console.print(f"[bold]Processing {len(all_docs)} documents...[/bold]")
        start_time = time.time()
        
        total_updated = 0
        errors = []
        
        if dry_run:
            console.print("[dim]Dry run mode - no changes will be made[/dim]")
            for doc_file in all_docs:
                doc = lm.parse_document(doc_file)
                if doc:
                    console.print(f"  Would update: {doc.id}")
            return
        
        # Process documents in parallel for SLA compliance
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_doc = {executor.submit(lm.update_bidirectional_links, doc): doc for doc in all_docs}
            
            for future in as_completed(future_to_doc):
                doc = future_to_doc[future]
                try:
                    result = future.result()
                    total_updated += result.updated_count
                    errors.extend(result.errors)
                except Exception as e:
                    errors.append(f"{doc}: {e}")
        
        elapsed = time.time() - start_time
        
        # Results
        console.print(f"\n[bold]Results:[/bold]")
        console.print(f"  Documents processed: {len(all_docs)}")
        console.print(f"  Links updated: {total_updated}")
        console.print(f"  Errors: {len(errors)}")
        console.print(f"  Time elapsed: {elapsed:.2f}s")
        
        if elapsed > 300:  # 5min SLA
            console.print(f"[yellow]⚠️  SLA Warning: {elapsed:.1f}s > 300s target[/yellow]")
        else:
            console.print(f"[green]✅ SLA Met: {elapsed:.1f}s < 300s target[/green]")
        
        if errors:
            console.print(f"\n[yellow]First 5 errors:[/yellow]")
            for error in errors[:5]:
                console.print(f"  [dim]- {error}[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@aspice_app.command("check")
def aspice_check(
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="Project path to check"),
    fix: bool = typer.Option(False, "--fix", help="Auto-fix issues where possible"),
):
    """Check ASPICE compliance (conflict detection)."""
    try:
        from curaops.skills.aspice_conflict_detector import ConflictDetector
        from rich.panel import Panel
        
        detector = ConflictDetector(root_dir=path)
        conflicts = detector.detect_conflicts()
        report = detector.generate_conflict_report(conflicts)
        
        # Summary
        console.print(Panel(
            f"[bold]ASPICE Compliance Check[/bold]\n"
            f"Total Conflicts: {report['total_conflicts']}\n"
            f"By Type: {report['by_type']}\n"
            f"By Severity: {report['by_severity']}",
            title="Summary",
            border_style="red" if report['total_conflicts'] > 0 else "green"
        ))
        
        # Details
        if conflicts:
            for c in conflicts:
                severity_color = {"CRITICAL": "red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}.get(c.severity.value, "white")
                console.print(f"\n[{severity_color}]{c.severity.value}[/{severity_color}]: {c.type.value}")
                console.print(f"  Location: {c.location}")
                console.print(f"  Message: {c.message}")
                if c.fix_suggestions:
                    console.print("  Suggestions:")
                    for s in c.fix_suggestions:
                        console.print(f"    • {s}")
        
        if report['total_conflicts'] > 0:
            raise typer.Exit(1)
            
    except ImportError:
        console.print("[red]Error: aspice_conflict_detector skill not found[/red]")
        raise typer.Exit(1)


# ═══════════════════════════════════════════════════════════════
# MULTI-AGENT LOCK COMMANDS
# ═══════════════════════════════════════════════════════════════

@lock_app.command("claim")
def lock_claim(
    file: str = typer.Option(..., "--file", "-f", help="File or directory to claim"),
    agent: str = typer.Option(..., "--agent", "-a", help="Agent ID"),
    scope: str = typer.Option("FILE", "--scope", "-s", help="Scope: FILE, DIRECTORY, PATTERN"),
    ttl: int = typer.Option(3600, "--ttl", help="Lock duration in seconds"),
):
    """Claim a file lock."""
    try:
        from curaops.skills.multi_agent_lock import MultiAgentLock, LockScope
        
        lock_mgr = MultiAgentLock(storage_dir=Path.home() / ".curaops" / "locks")
        scope_enum = LockScope(scope.upper())
        
        lock = lock_mgr.claim_file(file, agent_id=agent, scope=scope_enum, ttl=ttl)
        
        console.print(f"[green]✅ Lock claimed:[/green] {lock.lock_id}")
        console.print(f"  Path: {lock.path}")
        console.print(f"  Agent: {lock.agent_id}")
        console.print(f"  Scope: {lock.scope.value}")
        console.print(f"  Expires: {lock.expires_at}")
        
    except ImportError:
        console.print("[red]Error: multi_agent_lock skill not found[/red]")
        raise typer.Exit(1)


@lock_app.command("release")
def lock_release(
    lock_id: str = typer.Argument(..., help="Lock ID to release"),
):
    """Release a lock."""
    try:
        from curaops.skills.multi_agent_lock import MultiAgentLock
        
        lock_mgr = MultiAgentLock(storage_dir=Path.home() / ".curaops" / "locks")
        result = lock_mgr.release_lock(lock_id)
        
        if result:
            console.print(f"[green]✅ Lock released:[/green] {lock_id}")
        else:
            console.print(f"[yellow]Lock not found:[/yellow] {lock_id}")
            
    except ImportError:
        console.print("[red]Error: multi_agent_lock skill not found[/red]")
        raise typer.Exit(1)


@lock_app.command("status")
def lock_status(
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Check specific path"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Show locks for agent"),
):
    """Show lock status."""
    try:
        from curaops.skills.multi_agent_lock import MultiAgentLock
        
        lock_mgr = MultiAgentLock(storage_dir=Path.home() / ".curaops" / "locks")
        
        if path:
            is_locked = lock_mgr.is_locked(path)
            status = "[red]LOCKED[/red]" if is_locked else "[green]FREE[/green]"
            console.print(f"{path}: {status}")
        elif agent:
            locks = lock_mgr.get_agent_locks(agent)
            console.print(f"Locks for agent [bold]{agent}[/bold]:")
            for lock in locks:
                console.print(f"  • {lock.lock_id}: {lock.path} ({lock.scope.value})")
        else:
            locks = lock_mgr.get_active_locks()
            table = Table(title="Active Locks")
            table.add_column("ID", style="cyan")
            table.add_column("Agent", style="green")
            table.add_column("Path", style="yellow")
            table.add_column("Scope", style="blue")
            table.add_column("Expires", style="red")
            
            for lock in locks:
                table.add_row(
                    lock.lock_id,
                    lock.agent_id,
                    lock.path,
                    lock.scope.value,
                    str(lock.expires_at)
                )
            
            console.print(table)
            
    except ImportError:
        console.print("[red]Error: multi_agent_lock skill not found[/red]")
        raise typer.Exit(1)


# ═══════════════════════════════════════════════════════════════
# PATTERN LEARNING COMMANDS
# ═══════════════════════════════════════════════════════════════

@pattern_app.command("record")
def pattern_record(
    action: str = typer.Argument(..., help="Action performed"),
    context: str = typer.Option(..., "--context", "-c", help="Context (JSON or string)"),
    success: bool = typer.Option(True, "--success/--failure", help="Whether action succeeded"),
):
    """Record a code finding to learn pattern."""
    try:
        from curaops.skills.pattern_learning import PatternLearningEngine, CodeFinding
        
        pl = PatternLearningEngine(storage_dir=Path.home() / ".curaops" / "patterns")
        
        # Create a code finding from the action/context
        finding = CodeFinding(
            description=action,
            code_snippet=context,
            severity="MEDIUM"
        )
        pattern = pl.learn_from_finding(finding)
        
        if pattern:
            pl.store_pattern(pattern)
            console.print(f"[green]✅ Pattern recorded:[/green] {pattern.name} ({pattern.id})")
        else:
            console.print(f"[yellow]⚠️  Could not extract pattern from finding[/yellow]")
        
    except ImportError:
        console.print("[red]Error: pattern_learning skill not found[/red]")
        raise typer.Exit(1)


@pattern_app.command("suggest")
def pattern_suggest(
    context: str = typer.Argument(..., help="Current context"),
    limit: int = typer.Option(3, "--limit", "-n", help="Max suggestions"),
):
    """Get pattern-based suggestions."""
    try:
        from curaops.skills.pattern_learning import PatternLearningEngine
        
        pl = PatternLearningEngine(storage_dir=Path.home() / ".curaops" / "patterns")
        
        # Load all patterns and match against context
        patterns = pl.load_all_patterns()
        matches = []
        
        for pattern in patterns:
            if context.lower() in pattern.name.lower() or context.lower() in pattern.description.lower():
                matches.append(pattern)
        
        matches = matches[:limit]
        
        if matches:
            console.print("[bold]Matching Patterns:[/bold]")
            for p in matches:
                console.print(f"  • {p.name} (confidence: {p.confidence:.2f})")
                console.print(f"    {p.description[:60]}...")
        else:
            console.print("[yellow]No patterns found for this context[/yellow]")
            
    except ImportError:
        console.print("[red]Error: pattern_learning skill not found[/red]")
        raise typer.Exit(1)
