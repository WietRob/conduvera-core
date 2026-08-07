"""
CuraOps-Control CLI — Agent + Captain + Gate + Dashboard commands.

Usage:
    matrix-cli agent boot Batman --task TASK-I198 --issue 200 --tool opencode
    matrix-cli agent status Batman
    matrix-cli agent ready Batman
    matrix-cli agent blocked Batman --reason sonar_failed
    matrix-cli agent evidence Batman
    matrix-cli agent sync Batman
    matrix-cli agent stop Batman
    matrix-cli agent list
    matrix-cli captain tick
    matrix-cli captain next
    matrix-cli captain dispatch Batman "Fix local gate failures"
    matrix-cli captain dashboard
    matrix-cli gate run Batman
    matrix-cli gate profiles
    matrix-cli dashboard
"""

from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns

from conduvera.control.registry import AgentRegistry, AgentRecord, AgentStatus
from conduvera.control.eventlog import EventLog
from conduvera.control.gates import GateRunner, GateStatus, BUILTIN_GATES
from conduvera.control.stream_state import StreamStateStore, StreamState, AgentReply
from conduvera.control.worktree_sentinel import WorktreeSentinel

console = Console()

# ── Sub-apps ──────────────────────────────────────────────────────
agent_app = typer.Typer(help="Agent lifecycle: boot, status, ready, blocked, evidence, sync, stop")
captain_app = typer.Typer(help="Captain orchestration: tick, next, dispatch, dashboard")
gate_app = typer.Typer(help="Gate enforcement: run, profiles, list")
stream_app = typer.Typer(help="Stream state: show, transition, reply, blocked")
worktree_app = typer.Typer(help="Worktree safety: inspect, check-mutate")
gateway_app = typer.Typer(help="AI Gateway: route, smoke, audit")


# ═══════════════════════════════════════════════════════════════════
# AGENT COMMANDS
# ═══════════════════════════════════════════════════════════════════

@agent_app.command("boot")
def agent_boot(
    agent_id: str = typer.Argument(..., help="Agent name (e.g. Batman)"),
    task: str = typer.Option(..., "--task", "-t", help="Task key (e.g. TASK-I198)"),
    issue: Optional[int] = typer.Option(None, "--issue", "-i", help="GitHub issue number"),
    tool: str = typer.Option("manual", "--tool", help="Tool: opencode, manual, droid, zed"),
    worktree: Optional[str] = typer.Option(None, "--worktree", "-w", help="Worktree path"),
    gate_profile: str = typer.Option("default", "--gate-profile", "-g", help="Gate profile name"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Comma-separated allowed paths"),
):
    """Boot an agent: register, prepare worktree, start session."""
    registry = AgentRegistry()
    eventlog = EventLog()

    # Default worktree path
    wt = worktree or str(Path.cwd() / ".ai" / "worktrees" / f"{agent_id}-{task}")

    # Parse scope
    scope_files = [s.strip() for s in scope.split(",")] if scope else []

    record = AgentRecord(
        agent_id=agent_id,
        tool=tool,
        task=task,
        issue=issue,
        worktree=wt,
        gate_profile=gate_profile,
        scope_files=scope_files,
        session="",
        status=AgentStatus.BOOTING,
    )

    try:
        registry.register(record)
    except ValueError as e:
        console.print(f"[bold red]ERROR:[/bold red] {e}")
        raise typer.Exit(1)

    # Prepare worktree via adapter
    adapter = _get_adapter(tool)
    config = {"task": task, "gate_profile": gate_profile}

    # Ensure worktree dir exists
    wt_path = Path(wt)
    if not wt_path.exists():
        wt_path.mkdir(parents=True, exist_ok=True)
        console.print(f"  Created worktree: {wt}")

    prep = adapter.prepare_worktree(agent_id, wt, scope_files, config)
    if not prep.success:
        console.print(f"[yellow]WARN:[/yellow] Boot pack incomplete: {prep.message}")
    else:
        console.print(f"  Boot pack: {prep.message}")

    # Start session (for non-manual adapters)
    session_ref = "manual"
    if tool != "manual":
        start = adapter.start_session(agent_id, wt, task, config)
        if start.success:
            session_ref = start.detail.get("session_ref", "unknown")
            registry.update(agent_id, session=session_ref)
            console.print(f"  Session: {session_ref}")
        else:
            console.print(f"[yellow]WARN:[/yellow] Session start failed: {start.message}")

    registry.set_active(agent_id)
    eventlog.log("boot", agent_id, f"Booted with tool={tool} task={task} profile={gate_profile}")

    console.print(f"[green]OK[/green] Agent '{agent_id}' booted")
    console.print(f"  ID: {agent_id}")
    console.print(f"  Task: {task}")
    console.print(f"  Tool: {tool}")
    console.print(f"  Profile: {gate_profile}")
    console.print(f"  Worktree: {wt}")


@agent_app.command("status")
def agent_status(
    agent_id: str = typer.Argument(..., help="Agent name"),
):
    """Show agent status."""
    registry = AgentRegistry()
    record = registry.get(agent_id)
    if not record:
        console.print(f"[red]Agent '{agent_id}' not found[/red]")
        raise typer.Exit(1)

    _print_agent_detail(record)


@agent_app.command("list")
def agent_list(
    status_filter: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
):
    """List all registered agents."""
    registry = AgentRegistry()
    agents = registry.list_all()

    if status_filter:
        agents = [a for a in agents if a.status.value == status_filter]

    if not agents:
        console.print("[yellow]No agents registered[/yellow]")
        return

    table = Table(title="Registered Agents")
    table.add_column("Agent", style="cyan", no_wrap=True)
    table.add_column("Status", style="bold")
    table.add_column("Tool")
    table.add_column("Task")
    table.add_column("Profile")
    table.add_column("Worktree", max_width=40)

    for a in agents:
        status_color = {
            "active": "green",
            "ready": "blue",
            "blocked": "red",
            "booting": "yellow",
            "stopped": "dim",
            "crashed": "bold red",
        }.get(a.status.value, "white")
        table.add_row(
            a.agent_id,
            f"[{status_color}]{a.status.value}[/{status_color}]",
            a.tool,
            a.task,
            a.gate_profile,
            a.worktree,
        )

    console.print(table)


@agent_app.command("ready")
def agent_ready(
    agent_id: str = typer.Argument(..., help="Agent name"),
    skip_gates: bool = typer.Option(False, "--skip-gates", help="Skip gate checks (dangerous)"),
    legacy_only: bool = typer.Option(False, "--legacy-only", help="Only run legacy readiness script"),
):
    """Declare agent ready. Runs legacy pr-readiness-summary.sh + Python gates."""
    registry = AgentRegistry()
    eventlog = EventLog()
    record = registry.get(agent_id)

    if not record:
        console.print(f"[red]Agent '{agent_id}' not found[/red]")
        raise typer.Exit(1)

    if record.status not in (AgentStatus.ACTIVE, AgentStatus.BLOCKED):
        console.print(f"[red]Agent '{agent_id}' is {record.status.value}, cannot declare ready[/red]")
        raise typer.Exit(1)

    if skip_gates:
        registry.set_ready(agent_id)
        eventlog.log("ready", agent_id, "Declared ready (gates skipped)")
        console.print(f"[yellow]READY (gates skipped)[/yellow] {agent_id}")
        return

    # --- KANONISCHER PFAD: Legacy pr-readiness-summary.sh ---
    from conduvera.control.scripts_bridge import ScriptRunner, parse_readiness_stdout
    from conduvera.control.worktree_sentinel import WorktreeSentinel

    sentinel = WorktreeSentinel()
    runner = ScriptRunner(sentinel=sentinel)

    readiness_result = runner.pr_readiness(verify=True)
    readiness = parse_readiness_stdout(readiness_result.stdout)

    console.print(f"\n[bold]Legacy Readiness:[/bold] {readiness.decision}")
    for k, v in readiness.details.items():
        if k != "decision":
            console.print(f"  {k}={v}")

    if not readiness.is_go:
        registry.set_blocked(agent_id, f"Legacy readiness: {readiness.decision}")
        eventlog.log("blocked", agent_id, f"Legacy readiness: {readiness.decision}")
        console.print(f"[bold red]BLOCKED[/bold red] {agent_id} — legacy readiness: {readiness.decision}")
        raise typer.Exit(1)

    # --- SUPPLEMENT: Python GateRunner ---
    if not legacy_only:
        from conduvera.control.gates import GateRunner

        gate_runner = GateRunner()
        result = gate_runner.run_for_agent(record.to_dict())

        table = Table(title=f"Supplement Gates: {agent_id}")
        table.add_column("Gate", style="cyan")
        table.add_column("Status")
        table.add_column("Message", max_width=50)

        for g in result.gates:
            s_color = {
                "pass": "green", "fail": "bold red", "skipped": "yellow",
                "error": "red", "not_run": "dim",
            }.get(g.status.value, "white")
            table.add_row(
                g.gate_name,
                f"[{s_color}]{g.status.value}[/{s_color}]",
                g.message[:80],
            )

        console.print(table)

        if not result.overall_pass:
            failed = [g.gate_name for g in result.failed_gates]
            registry.set_blocked(agent_id, f"Gates failed: {', '.join(failed)}")
            eventlog.log("blocked", agent_id, f"Gates failed: {', '.join(failed)}", failed=failed)
            console.print(f"[bold red]BLOCKED[/bold red] {agent_id} — gates failed: {', '.join(failed)}")
            raise typer.Exit(1)

    # --- BEIDES BESTANDEN ---
    registry.set_ready(agent_id, evidence={
        "legacy_readiness": readiness.to_dict() if hasattr(readiness, 'to_dict') else {"decision": readiness.decision, "details": readiness.details},
    })
    eventlog.log("ready", agent_id, "Legacy GO + supplement gates passed")
    console.print(f"[green]READY[/green] {agent_id} — legacy GO + gates passed")


@agent_app.command("blocked")
def agent_blocked(
    agent_id: str = typer.Argument(..., help="Agent name"),
    reason: str = typer.Option("manual", "--reason", "-r", help="Block reason"),
):
    """Manually block an agent."""
    registry = AgentRegistry()
    eventlog = EventLog()
    registry.set_blocked(agent_id, reason)
    eventlog.log("blocked", agent_id, reason)
    console.print(f"[red]BLOCKED[/red] {agent_id}: {reason}")


@agent_app.command("evidence")
def agent_evidence(
    agent_id: str = typer.Argument(..., help="Agent name"),
):
    """Show last gate evidence for an agent."""
    eventlog = EventLog()
    events = eventlog.events_for_agent(agent_id, limit=20)
    gate_events = [e for e in events if e.event_type in ("ready", "blocked", "gate_run")]

    if not gate_events:
        console.print(f"[yellow]No gate evidence for {agent_id}[/yellow]")
        return

    table = Table(title=f"Evidence: {agent_id}")
    table.add_column("Time", style="dim", max_width=20)
    table.add_column("Type")
    table.add_column("Detail", max_width=60)

    for e in gate_events:
        table.add_row(
            e.timestamp[:19],
            e.event_type,
            e.detail[:80],
        )

    console.print(table)


@agent_app.command("sync")
def agent_sync(
    agent_id: str = typer.Argument(..., help="Agent name"),
):
    """Sync agent state: check session liveness, update status."""
    registry = AgentRegistry()
    eventlog = EventLog()
    record = registry.get(agent_id)

    if not record:
        console.print(f"[red]Agent '{agent_id}' not found[/red]")
        raise typer.Exit(1)

    adapter = _get_adapter(record.tool)
    status_result = adapter.session_status(agent_id, record.session)

    alive = status_result.detail.get("alive", False)
    if not alive and record.status in (AgentStatus.ACTIVE, AgentStatus.BOOTING):
        registry.set_crashed(agent_id, "Session died")
        eventlog.log("crashed", agent_id, "Session detected dead during sync")
        console.print(f"[bold red]CRASHED[/bold red] {agent_id} — session died")
    else:
        eventlog.log("sync", agent_id, f"Sync OK, alive={alive}")
        console.print(f"[green]SYNCED[/green] {agent_id} — session alive={alive}")


@agent_app.command("stop")
def agent_stop(
    agent_id: str = typer.Argument(..., help="Agent name"),
):
    """Gracefully stop an agent."""
    registry = AgentRegistry()
    eventlog = EventLog()
    record = registry.get(agent_id)

    if not record:
        console.print(f"[red]Agent '{agent_id}' not found[/red]")
        raise typer.Exit(1)

    # Stop session via adapter
    adapter = _get_adapter(record.tool)
    adapter.stop_session(agent_id, record.session)
    registry.set_stopped(agent_id)
    eventlog.log("stopped", agent_id, "Gracefully stopped")
    console.print(f"[green]STOPPED[/green] {agent_id}")


@agent_app.command("launch")
def agent_launch(
    agent_id: str = typer.Argument(..., help="Agent name"),
    client_name: Optional[str] = typer.Option(None, "--client", help="Gateway client name"),
    gateway_profile: Optional[str] = typer.Option(None, "--profile", help="Gateway routing profile"),
    sensitive_class: Optional[str] = typer.Option(None, "--sensitive", help="Sensitive class"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without starting session"),
):
    """Launch an agent via the Harness (registry + stream + sentinel + gateway)."""
    from .stream_state import StreamStateStore
    from .worktree_sentinel import WorktreeSentinel
    from .launcher import AgentLauncher

    registry = AgentRegistry()
    stream_store = StreamStateStore()
    sentinel = WorktreeSentinel()
    event_log = EventLog()

    launcher_ = AgentLauncher(
        registry=registry,
        stream_store=stream_store,
        sentinel=sentinel,
        event_log=event_log,
    )

    result = launcher_.launch(
        agent_id,
        client_name=client_name,
        gateway_profile=gateway_profile,
        sensitive_class=sensitive_class,
        dry_run=dry_run,
    )

    if result.success:
        console.print(f"[green]LAUNCHED[/green] {agent_id}")
        console.print(f"  session: {result.session_ref}")
        if result.warnings:
            for w in result.warnings:
                console.print(f"  [yellow]WARN:[/yellow] {w}")
        if result.env_set:
            console.print(f"  OPENAI_BASE_URL: {result.env_set.get('OPENAI_BASE_URL', 'N/A')}")
    else:
        console.print(f"[red]LAUNCH FAILED[/red] {agent_id}: {result.error}")
        raise typer.Exit(1)


# ═══════════════════════════════════════════════════════════════════
# CAPTAIN COMMANDS
# ═══════════════════════════════════════════════════════════════════

@captain_app.command("tick")
def captain_tick():
    """Captain tick: sync all agents, show action queue."""
    registry = AgentRegistry()
    eventlog = EventLog()
    agents = registry.list_active()

    if not agents:
        console.print("[yellow]No active agents[/yellow]")
        return

    actions = []
    for a in agents:
        adapter = _get_adapter(a.tool)
        status = adapter.session_status(a.agent_id, a.session)
        alive = status.detail.get("alive", False)

        if not alive and a.status in (AgentStatus.ACTIVE, AgentStatus.BOOTING):
            registry.set_crashed(a.agent_id, "Session died during tick")
            eventlog.log("crashed", a.agent_id, "Detected in tick")
            actions.append(f"[red]1.[/red] CRASHED: {a.agent_id} — session died. Restart or remove.")
        elif a.status == AgentStatus.BLOCKED:
            actions.append(f"[yellow]{len(actions)+1}.[/yellow] BLOCKED: {a.agent_id} — {a.blocked_reason}")
        elif a.status == AgentStatus.READY:
            actions.append(f"[blue]{len(actions)+1}.[/blue] READY: {a.agent_id} — awaiting review/dispatch")
        elif a.status == AgentStatus.ACTIVE:
            actions.append(f"[green]{len(actions)+1}.[/green] ACTIVE: {a.agent_id} — {a.task}")

    eventlog.log("tick", "captain", f"Tick: {len(agents)} agents, {len(actions)} actions")

    console.print(Panel(
        "\n".join(actions) if actions else "No actions needed",
        title="Captain Tick",
        border_style="blue",
    ))


@captain_app.command("next")
def captain_next():
    """Show the single highest-priority next action."""
    registry = AgentRegistry()
    eventlog = EventLog()
    agents = registry.list_active()

    # Priority: crashed > blocked > ready > active
    crashed = [a for a in agents if a.status == AgentStatus.CRASHED]
    blocked = [a for a in agents if a.status == AgentStatus.BLOCKED]
    ready = [a for a in agents if a.status == AgentStatus.READY]
    active = [a for a in agents if a.status == AgentStatus.ACTIVE]

    if crashed:
        a = crashed[0]
        console.print(f"[bold red]NEXT (crash):[/bold red] {a.agent_id} — restart or remove")
    elif blocked:
        a = blocked[0]
        console.print(f"[bold yellow]NEXT (blocked):[/bold yellow] {a.agent_id} — {a.blocked_reason}")
        console.print(f"  Fix and run: matrix-cli agent ready {a.agent_id}")
    elif ready:
        a = ready[0]
        console.print(f"[bold blue]NEXT (ready):[/bold blue] {a.agent_id} — {a.task}")
        console.print(f"  Review and: matrix-cli captain dispatch {a.agent_id} \"<next task>\"")
    elif active:
        a = active[0]
        console.print(f"[green]NEXT (active):[/green] {a.agent_id} — {a.task} (in progress)")
    else:
        console.print("[dim]No active agents. Boot one: matrix-cli agent boot <name> --task <task>[/dim]")

    eventlog.log("next", "captain", "Next action queried")


@captain_app.command("dispatch")
def captain_dispatch(
    agent_id: str = typer.Argument(..., help="Agent name"),
    task: str = typer.Argument(..., help="New task description"),
):
    """Dispatch a new task to an agent."""
    registry = AgentRegistry()
    eventlog = EventLog()
    record = registry.get(agent_id)

    if not record:
        console.print(f"[red]Agent '{agent_id}' not found[/red]")
        raise typer.Exit(1)

    registry.update(agent_id, task=task)
    registry.set_active(agent_id)
    eventlog.log("dispatch", agent_id, f"New task: {task}")

    console.print(f"[green]DISPATCHED[/green] {agent_id}: {task}")
    console.print(f"  Agent is now ACTIVE on new task")


@captain_app.command("dashboard")
def captain_dashboard():
    """Full dashboard: all agents, their status, last events."""
    registry = AgentRegistry()
    eventlog = EventLog()
    agents = registry.list_all()

    if not agents:
        console.print("[yellow]No agents registered[/yellow]")
        console.print("Boot one: matrix-cli agent boot <name> --task <task>")
        return

    # Agent table
    table = Table(title="CuraOps Dashboard", show_lines=True)
    table.add_column("Agent", style="cyan", no_wrap=True)
    table.add_column("Status", style="bold")
    table.add_column("Tool")
    table.add_column("Task")
    table.add_column("Profile")
    table.add_column("Blocked Reason", max_width=30)
    table.add_column("Updated", max_width=19)

    for a in agents:
        s_color = {
            "active": "green", "ready": "blue", "blocked": "red",
            "booting": "yellow", "stopped": "dim", "crashed": "bold red",
        }.get(a.status.value, "white")
        table.add_row(
            a.agent_id,
            f"[{s_color}]{a.status.value}[/{s_color}]",
            a.tool,
            a.task[:30],
            a.gate_profile,
            a.blocked_reason[:30] if a.blocked_reason else "",
            a.updated_at[:19] if a.updated_at else "",
        )

    console.print(table)

    # Recent events
    events = eventlog.read_last(10)
    if events:
        console.print()
        etable = Table(title="Recent Events")
        etable.add_column("Time", style="dim", max_width=19)
        etable.add_column("Agent")
        etable.add_column("Type")
        etable.add_column("Detail", max_width=50)

        for e in reversed(events):
            e_color = {
                "boot": "green", "ready": "blue", "blocked": "red",
                "crashed": "bold red", "stopped": "dim", "dispatch": "cyan",
                "tick": "dim", "sync": "dim",
            }.get(e.event_type, "white")
            etable.add_row(
                e.timestamp[:19],
                f"[cyan]{e.agent_id}[/cyan]",
                f"[{e_color}]{e.event_type}[/{e_color}]",
                e.detail[:60],
            )
        console.print(etable)


# ═══════════════════════════════════════════════════════════════════
# GATE COMMANDS
# ═══════════════════════════════════════════════════════════════════

@gate_app.command("run")
def gate_run(
    agent_id: str = typer.Argument(..., help="Agent name"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Override gate profile"),
    use_legacy: bool = typer.Option(True, "--legacy/--no-legacy", help="Use legacy scripts for gate execution"),
):
    """Run gates for an agent. Uses ScriptRunner for legacy gates by default."""
    registry = AgentRegistry()
    eventlog = EventLog()
    record = registry.get(agent_id)

    if not record:
        console.print(f"[red]Agent '{agent_id}' not found[/red]")
        raise typer.Exit(1)

    all_results = []

    if use_legacy:
        # --- LEGACY PFADE: ScriptRunner ---
        from conduvera.control.scripts_bridge import ScriptRunner, ScriptName, ExitCode
        from conduvera.control.worktree_sentinel import WorktreeSentinel

        sentinel = WorktreeSentinel()
        script_runner = ScriptRunner(sentinel=sentinel)

        # Run finish gate via legacy script
        fg = script_runner.finish_gate(agent_id=agent_id, mode="--verify-only")
        all_results.append({
            "gate": "finish_gate (legacy)",
            "pass": fg.success,
            "message": fg.stdout.strip()[:200] if fg.success else fg.stderr.strip()[:200],
        })

        # Run sonar gate via legacy script
        sg = script_runner.sonar_gate(agent_id=agent_id, mode="--optional")
        all_results.append({
            "gate": "sonar_gate (legacy)",
            "pass": sg.exit_code in (ExitCode.OK, ExitCode.BAD_ARGS),  # optional+skip = pass
            "message": sg.stdout.strip()[:200] if sg.stdout else sg.stderr.strip()[:200],
        })

    # --- PYTHON GATES: GateRunner ---
    runner = GateRunner()
    result = runner.run_for_agent(record.to_dict(), profile_name=profile)

    for g in result.gates:
        all_results.append({
            "gate": g.gate_name,
            "pass": g.passed,
            "message": g.message[:200],
        })

    overall = all(r["pass"] for r in all_results)
    eventlog.log("gate_run", agent_id, f"Gate run: {'PASS' if overall else 'FAIL'}")

    table = Table(title=f"Gates: {agent_id}")
    table.add_column("Gate", style="cyan")
    table.add_column("Status")
    table.add_column("Message", max_width=60)

    for r in all_results:
        s_color = "green" if r["pass"] else "bold red"
        table.add_row(r["gate"], f"[{s_color}]{'PASS' if r['pass'] else 'FAIL'}[/{s_color}]", r["message"][:80])

    console.print(table)

    if overall:
        console.print(f"[green]ALL GATES PASSED[/green]")
    else:
        console.print(f"[bold red]GATES FAILED[/bold red] — {sum(1 for r in all_results if not r['pass'])} failures")
        raise typer.Exit(1)


@gate_app.command("profiles")
def gate_profiles():
    """List available gate profiles."""
    runner = GateRunner()
    profiles = runner.list_profiles()

    if not profiles:
        console.print("[yellow]No gate profiles configured[/yellow]")
        console.print("Create: .conduvera/control/policies/gates.yaml")
        return

    table = Table(title="Gate Profiles")
    table.add_column("Profile", style="cyan")
    table.add_column("Required Gates")
    table.add_column("Excluded Gates")

    for name in profiles:
        p = runner.get_profile(name)
        table.add_row(
            name,
            ", ".join(p.required) if p else "?",
            ", ".join(p.not_required) if p else "",
        )

    console.print(table)


@gate_app.command("list")
def gate_list():
    """List all available gate implementations."""
    table = Table(title="Available Gates")
    table.add_column("Gate", style="cyan")
    table.add_column("Description")

    for name, gate in BUILTIN_GATES.items():
        table.add_row(name, gate.__class__.__name__)

    console.print(table)


# ═══════════════════════════════════════════════════════════════════
# DASHBOARD COMMAND (top-level convenience)
# ═══════════════════════════════════════════════════════════════════

dashboard_app = typer.Typer(help="Dashboard overview")

@dashboard_app.command("show")
def dashboard_show():
    """Show full CuraOps dashboard."""
    captain_dashboard()


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════

def _get_adapter(tool: str):
    """Get the adapter for a tool name."""
    if tool == "opencode":
        from conduvera.control.adapters.opencode import OpenCodeAdapter
        return OpenCodeAdapter()
    else:
        from conduvera.control.adapters.manual import ManualAdapter
        return ManualAdapter()


def _print_agent_detail(record: AgentRecord):
    """Print detailed agent info."""
    s_color = {
        "active": "green", "ready": "blue", "blocked": "red",
        "booting": "yellow", "stopped": "dim", "crashed": "bold red",
    }.get(record.status.value, "white")

    console.print(Panel(
        f"[bold]Agent:[/bold]  {record.agent_id}\n"
        f"[bold]Status:[/bold] [{s_color}]{record.status.value}[/{s_color}]\n"
        f"[bold]Tool:[/bold]   {record.tool}\n"
        f"[bold]Task:[/bold]   {record.task}\n"
        f"[bold]Issue:[/bold]  {record.issue or '-'}\n"
        f"[bold]Worktree:[/bold] {record.worktree}\n"
        f"[bold]Session:[/bold]  {record.session or 'none'}\n"
        f"[bold]Profile:[/bold]  {record.gate_profile}\n"
        f"[bold]Scope:[/bold]    {', '.join(record.scope_files) if record.scope_files else 'unrestricted'}\n"
        f"[bold]Blocked:[/bold]  {record.blocked_reason or '-'}\n"
        f"[bold]Created:[/bold]  {record.created_at[:19] if record.created_at else '-'}\n"
        f"[bold]Updated:[/bold]  {record.updated_at[:19] if record.updated_at else '-'}",
        title=f"Agent: {record.agent_id}",
        border_style=s_color,
    ))


# ═══════════════════════════════════════════════════════════════════
# STREAM STATE COMMANDS
# ═══════════════════════════════════════════════════════════════════

@stream_app.command("show")
def stream_show(
    agent_id: Optional[str] = typer.Argument(None, help="Agent name (omit for all)"),
):
    """Show stream state for agent or all."""
    store = StreamStateStore()
    if agent_id:
        rec = store.get(agent_id)
        s_color = "red" if rec.state.value.startswith("BLOCKED") else (
            "green" if rec.state == StreamState.WORKING else "yellow")
        console.print(Panel(
            f"[bold]Agent:[/bold]  {rec.agent}\n"
            f"[bold]State:[/bold]  [{s_color}]{rec.state.value}[/{s_color}]\n"
            f"[bold]Reason:[/bold] {rec.reason or '-'}\n"
            f"[bold]Head SHA:[/bold] {rec.head_sha or '-'}\n"
            f"[bold]Required Reply:[/bold] {rec.required_agent_reply or 'none'}\n"
            f"[bold]Updated:[/bold] {rec.updated_at[:19] if rec.updated_at else '-'}",
            title=f"Stream: {agent_id}",
            border_style=s_color,
        ))
    else:
        records = store.list_all()
        if not records:
            console.print("[dim]No streams found.[/dim]")
            return
        table = Table(title="Stream States")
        table.add_column("Agent", style="bold")
        table.add_column("State")
        table.add_column("Reason")
        table.add_column("Head SHA")
        for r in records:
            s_color = "red" if r.state.value.startswith("BLOCKED") else (
                "green" if r.state == StreamState.WORKING else "")
            table.add_row(r.agent, f"[{s_color}]{r.state.value}[/{s_color}]", r.reason[:30], r.head_sha[:12])
        console.print(table)


@stream_app.command("transition")
def stream_transition(
    agent_id: str = typer.Argument(..., help="Agent name"),
    state: str = typer.Argument(..., help="Target state"),
    reason: str = typer.Option("", "--reason", "-r", help="Reason"),
    head_sha: str = typer.Option("", "--head-sha", help="Current HEAD SHA"),
):
    """Transition agent stream state."""
    store = StreamStateStore()
    try:
        new_state = StreamState(state)
    except ValueError:
        console.print(f"[red]Unknown state: {state}[/red]")
        console.print(f"Valid: {', '.join(s.value for s in StreamState)}")
        raise typer.Exit(1)
    try:
        rec = store.set_state(agent_id, new_state, reason=reason, head_sha=head_sha)
        console.print(f"[green]{agent_id}[/green] -> [{new_state.value}]")
    except Exception as e:
        console.print(f"[red]Transition failed: {e}[/red]")
        raise typer.Exit(1)


@stream_app.command("reply")
def stream_reply(
    agent_id: str = typer.Argument(..., help="Agent name"),
    reply: str = typer.Argument(..., help="Reply type: ACK, PROGRESS, BLOCKER, READY_CANDIDATE"),
):
    """Accept an agent reply for stream state."""
    store = StreamStateStore()
    try:
        agent_reply = AgentReply(reply)
    except ValueError:
        console.print(f"[red]Unknown reply: {reply}[/red]")
        raise typer.Exit(1)
    try:
        rec = store.accept_reply(agent_id, agent_reply)
        console.print(f"[green]{agent_id}[/green] reply={reply} -> state=[{rec.state.value}]")
    except Exception as e:
        console.print(f"[red]Reply rejected: {e}[/red]")
        raise typer.Exit(1)


@stream_app.command("blocked")
def stream_blocked():
    """List all blocked streams."""
    store = StreamStateStore()
    blocked = store.list_blocked()
    if not blocked:
        console.print("[green]No blocked streams.[/green]")
        return
    table = Table(title="Blocked Streams")
    table.add_column("Agent", style="bold red")
    table.add_column("State")
    table.add_column("Reason")
    table.add_column("Required Reply")
    for r in blocked:
        table.add_row(r.agent, r.state.value, r.reason[:40], r.required_agent_reply)
    console.print(table)


# ═══════════════════════════════════════════════════════════════════
# WORKTREE COMMANDS
# ═══════════════════════════════════════════════════════════════════

@worktree_app.command("inspect")
def worktree_inspect(
    agent_id: str = typer.Argument(..., help="Agent name"),
):
    """Read-only inspect agent's worktree."""
    sentinel = WorktreeSentinel()
    report = sentinel.inspect(agent_id)

    if report.errors:
        for err in report.errors:
            console.print(f"[red]Error: {err}[/red]")
        raise typer.Exit(1)

    cls_color = {"CLEAN": "green", "CAPTAIN_CAUSED": "yellow", "AGENT_WIP": "blue", "UNKNOWN": "dim"}.get(
        report.overall_classification.value, "white")

    console.print(Panel(
        f"[bold]Agent:[/bold]  {report.agent_id}\n"
        f"[bold]Path:[/bold]   {report.worktree_path}\n"
        f"[bold]Branch:[/bold] {report.current_branch}\n"
        f"[bold]HEAD:[/bold]   {report.head_sha}\n"
        f"[bold]Clean:[/bold]  {'Yes' if report.is_clean else 'No'}\n"
        f"[bold]Dirty:[/bold]  {report.total_dirty}\n"
        f"[bold]Untracked:[/bold] {report.total_untracked}\n"
        f"[bold]Class:[/bold]  [{cls_color}]{report.overall_classification.value}[/{cls_color}]",
        title=f"Worktree: {agent_id}",
        border_style=cls_color,
    ))

    if report.dirty_files:
        table = Table(title="Dirty Files")
        table.add_column("File")
        table.add_column("Status")
        table.add_column("Class")
        for f in report.dirty_files[:20]:
            table.add_row(f.path, f.status, f.classification.value)
        console.print(table)


@worktree_app.command("check-mutate")
def worktree_check_mutate(
    agent_id: str = typer.Argument(..., help="Agent name"),
    operation: str = typer.Argument(..., help="Operation to check"),
):
    """Check if a mutating operation is allowed on agent's worktree."""
    sentinel = WorktreeSentinel()
    allowed = sentinel.can_mutate(agent_id, operation)
    if allowed:
        console.print(f"[green]ALLOWED[/green] {operation} on {agent_id}")
    else:
        console.print(f"[red]BLOCKED[/red] {operation} on {agent_id} (agent active or destructive op)")


# ═══════════════════════════════════════════════════════════════════
# GATEWAY COMMANDS
# ═══════════════════════════════════════════════════════════════════

@gateway_app.command("route")
def gateway_route(
    profile: str = typer.Option("local_deep", "--profile", "-p", help="Model profile"),
    sensitive_class: Optional[str] = typer.Option(None, "--sensitive", "-s", help="Sensitive class"),
):
    """Route a model request through the AI Gateway."""
    from conduvera.control.gateway.config import load_gateway_config
    from conduvera.control.gateway.router import GatewayRouter
    from conduvera.control.gateway.audit import AuditLogger

    config = load_gateway_config()
    router = GatewayRouter(config)
    result = router.route(profile, sensitive_class)

    color = {"ALLOWED": "green", "BLOCKED_CLOUD_FORBIDDEN": "red", "FALLBACK_TO_CLOUD": "yellow"}.get(
        result.policy_decision.value, "white")

    console.print(Panel(
        f"[bold]Profile:[/bold] {result.profile_name or '-'}\n"
        f"[bold]Provider:[/bold] {result.provider or '-'}\n"
        f"[bold]Model:[/bold] {result.model or '-'}\n"
        f"[bold]Base URL:[/bold] {result.base_url or '-'}\n"
        f"[bold]Decision:[/bold] [{color}]{result.policy_decision.value}[/{color}]\n"
        f"[bold]Reason:[/bold] {result.reason}",
        title="Gateway Route",
        border_style=color,
    ))

    # Audit log
    audit = AuditLogger()
    audit.log(client="cli", profile=profile, provider=result.provider,
              model=result.model, policy_decision=result.policy_decision.value,
              sensitive_class=sensitive_class)


@gateway_app.command("smoke")
def gateway_smoke():
    """Smoke test all gateway profiles."""
    from conduvera.control.gateway.config import load_gateway_config
    from conduvera.control.gateway.smoke import smoke_check_all

    config = load_gateway_config()
    results = smoke_check_all(config)

    table = Table(title="Gateway Smoke Tests")
    table.add_column("Profile", style="bold")
    table.add_column("Reachable")
    table.add_column("Status")
    table.add_column("Models")
    table.add_column("Error")

    for r in results:
        reachable = "[green]Yes[/green]" if r.reachable else "[red]No[/red]"
        status = str(r.status_code) if r.status_code else "-"
        models = str(r.model_count) if r.model_count else "-"
        error = r.error[:40] if r.error else "-"
        table.add_row(r.profile_name, reachable, status, models, error)

    console.print(table)


@gateway_app.command("audit")
def gateway_audit(
    last: int = typer.Option(20, "--last", "-n", help="Show last N entries"),
):
    """Show gateway audit log."""
    from conduvera.control.gateway.audit import AuditLogger

    audit = AuditLogger()
    entries = audit.read_entries(limit=last)

    if not entries:
        console.print("[dim]No audit entries.[/dim]")
        return

    table = Table(title=f"Gateway Audit (last {len(entries)})")
    table.add_column("Time", style="dim")
    table.add_column("Client")
    table.add_column("Profile")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Decision")
    table.add_column("Sensitive")

    for e in entries[-last:]:
        decision_color = "green" if e.get("policy_decision") == "ALLOWED" else "red"
        table.add_row(
            e.get("timestamp", "")[:19],
            e.get("client", "-"),
            e.get("profile", "-"),
            e.get("provider", "-"),
            e.get("model", "-"),
            f"[{decision_color}]{e.get('policy_decision', '-')}[/{decision_color}]",
            e.get("sensitive_class", "-"),
        )
    console.print(table)


@gateway_app.command("serve")
def gateway_serve(
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8900, help="Bind port"),
) -> None:
    """Start the Pi-native AI Gateway server."""
    import uvicorn
    from conduvera.control.gateway.app import create_app
    from conduvera.control.gateway.config import load_gateway_config
    from conduvera.control.gateway.auth import ClientRegistry
    from conduvera.control.gateway.audit import AuditLogger
    from pathlib import Path

    console.print(f"[bold cyan]Starting CuraOps AI Gateway on {host}:{port}[/bold cyan]")
    console.print("[dim]Policy proxy — local-first, no LiteLLM, no cloud fallback[/dim]")

    # Konfiguration laden
    try:
        config = load_gateway_config()
        console.print(f"  Profiles: {len(config.profiles)}")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load gateway profiles: {e}[/yellow]")
        config = None

    # Clients laden
    client_registry = ClientRegistry()
    clients_path = Path("config/gateway-clients.yaml")
    if clients_path.exists():
        client_registry.load(clients_path)
    console.print(f"  Clients:  {len(client_registry.clients)}")

    app = create_app(
        config=config,
        client_registry=client_registry,
    )

    uvicorn.run(app, host=host, port=port, log_level="info")
