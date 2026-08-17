"""Control plane CLI client (CONDUVERA-CLI control-plane commands).

Talks to the daemon over the Unix socket. All commands support human and
JSON output.

Commands: doctor, health, submit, list, inspect, cancel, cleanup, reconcile,
logs/evidence, capabilities.
"""

from __future__ import annotations

import json
import socket
import typer
from pathlib import Path

from conduvera.control_plane.service import ControlPlaneConfig

console = typer.echo
control_app = typer.Typer(help="Conduvera operational harness control plane")


def _socket_path() -> str:
    return str(ControlPlaneConfig.default().socket_path)


def _call(method: str, params: dict | None = None) -> dict:
    path = _socket_path()
    if not Path(path).exists():
        return {"ok": False, "error": {"code": "SERVICE_DOWN",
                                       "message": f"control plane not running ({path})"}}
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(30)
        sock.connect(path)
        sock.sendall(json.dumps({"method": method, "params": params or {}}).encode("utf-8"))
        data = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
            if len(data) > 2 * 1024 * 1024:
                break
        return json.loads(data.decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": {"code": "SERVICE_ERROR", "message": str(exc)}}
    finally:
        sock.close()


def _emit(result: dict, as_json: bool) -> None:
    if as_json:
        console(json.dumps(result, indent=2, ensure_ascii=False))
        return
    if not result.get("ok"):
        err = result.get("error", {})
        console(f"[ERROR] {err.get('code', 'ERROR')}: {err.get('message', result)}")
        raise typer.Exit(1)
    payload = result.get("result", {})
    if isinstance(payload, dict) and payload.get("message"):
        console(payload["message"])


@control_app.command("doctor")
def doctor(json_output: bool = typer.Option(False, "--json", help="JSON output")) -> None:
    """Service doctor: harness availability + registry health."""
    _emit(_call("doctor"), json_output)


@control_app.command("health")
def health(json_output: bool = typer.Option(False, "--json", help="JSON output")) -> None:
    """Service health."""
    _emit(_call("health"), json_output)


@control_app.command("submit")
def submit(
    task_id: str = typer.Option(..., "--task", help="task identifier"),
    attempt_id: str = typer.Option(..., "--attempt", help="attempt identifier"),
    harness: str = typer.Option("hermes_scoped", "--harness", help="hermes_scoped|codex_cli|opencode_cli"),
    prompt: str = typer.Option("Antworte mit genau einem Wort: PONG", "--prompt", help="job prompt"),
    repo: str = typer.Option("conduvera-core", "--repo", help="repository"),
    base_commit: str = typer.Option("", "--base-commit", help="base commit"),
    timeout: float = typer.Option(120.0, "--timeout", help="timeout seconds"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Submit a job through the router + control plane."""
    result = _call("start", {
        "task_id": task_id, "attempt_id": attempt_id, "harness": harness,
        "repo": repo, "base_commit": base_commit,
        "model_binding": {"route": "workload/local"},
        "prompt": prompt, "timeout_s": timeout,
    })
    _emit(result, json_output)


@control_app.command("run")
def run(
    goal: str = typer.Argument(..., help="the bounded engineering goal"),
    repo: str = typer.Option("conduvera-core", "--repo", help="allowlisted repo id"),
    policy: str = typer.Option("local-first", "--policy", help="local-first|cloud"),
    harness: str = typer.Option("hermes_scoped", "--harness", help="harness"),
    timeout: float = typer.Option(180.0, "--timeout", help="job timeout seconds"),
    base_commit: str = typer.Option("", "--base-commit", help="explicit base commit (default repo HEAD)"),
    wait_s: float = typer.Option(180.0, "--wait", help="max seconds to wait for a terminal state"),
    poll_s: float = typer.Option(3.0, "--poll", help="console poll interval"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Daily operator entry point: run one bounded local-first goal end to end.

    policy=local-first -> route workload/local (the local RTX 5090 model lane).
    Prints the operator surface: goal/job/attempt, harness, logical route,
    live model identity, context (served/verified), GPU mode + reservation,
    worktree/scope, lifecycle, evidence, and any admission/fallback reason.
    """
    import datetime as _dt
    import subprocess as _sp
    from pathlib import Path as _Path

    repo_paths = {
        "conduvera-core": _Path.home() / "projects/matrix-os",
        "conduvera-adapter": _Path.home() / "projects/conduvera-hermes-adapter",
        "conduvera-platform": _Path.home() / "projects/conduvera-platform",
        "conduit-fixture": _Path.home() / "projects/conduit-fixture",
    }
    route = "workload/local" if policy == "local-first" else "workload/architect"
    _ts = _dt.datetime.now()
    task_id = f"run-{_ts.strftime('%Y%m%d-%H%M%S')}"
    attempt_id = f"a{_ts.strftime('%H%M%S%f')}"  # UNIQUE per submit (global dedup)
    if not base_commit:
        rp = repo_paths.get(repo, _Path.home() / "projects" / repo)
        base_commit = _sp.run(["git", "-C", str(rp), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        if not base_commit:
            base_commit = _sp.run(["git", "-C", str(rp), "rev-parse", "--verify", "HEAD"],
                                  capture_output=True, text=True).stdout.strip()

    start = _call("start", {
        "task_id": task_id, "attempt_id": attempt_id, "harness": harness,
        "repo": repo, "base_commit": base_commit,
        "model_binding": {"route": route},
        "prompt": goal, "timeout_s": timeout,
    })
    if not start.get("ok"):
        _emit(start, json_output)
        return
    job_id = start.get("result", {}).get("job_id", "")
    print(f"[run] submitted task={task_id} job={job_id} route={route} harness={harness}")

    # -- gather live operator surface (read-only ODS observations) --
    def _get(url, timeout=3):
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.status, r.read()
        except Exception:
            return 0, b""

    model_id, served, verified, gpu_mode = "unknown", "?", "?", "?"
    st, body = _get("http://127.0.0.1:11434/v1/models")
    if st == 200:
        try:
            model_id = json.loads(body)["data"][0]["id"]
        except Exception:
            pass
    try:
        import yaml as _y
        c = _y.safe_load(open(_Path.home()/".local/share/ai-stack/route-capabilities.yaml"))
        for r_ in c.get("routes", []):
            if route in ([r_.get("route")] + r_.get("aliases", [])):
                served = r_.get("served_context"); verified = r_.get("verified_context")
                gpu_mode = r_.get("gpu_mode"); break
    except Exception:
        pass
    try:
        gpu_mode = _Path.home()/".local/share/ai-stack/active-mode"
        gpu_mode = gpu_mode.read_text().strip() if gpu_mode.exists() else gpu_mode
    except Exception:
        pass
    try:
        gpu = _sp.run(["nvidia-smi", "--query-gpu=memory.used,memory.free", "--format=csv,noheader"],
                      capture_output=True, text=True).stdout.strip()
    except Exception:
        gpu = "n/a"

    # -- poll console until terminal --
    terminal = None
    waited = 0.0
    while waited < wait_s:
        cons = _call("console", {})
        r = cons.get("result", {})
        for t in r.get("terminal", []):
            if t.get("job_id") == job_id:
                terminal = t
                break
        if terminal:
            break
        import time as _t
        _t.sleep(min(poll_s, 5.0)); waited += poll_s

    surface = {
        "goal": goal, "job_id": job_id, "attempt_id": attempt_id,
        "harness": harness, "route": route, "model_identity": model_id,
        "served_context": served, "verified_context": verified,
        "gpu_mode": gpu_mode, "gpu_reservation": gpu,
        "lifecycle": terminal.get("state", "RUNNING_OR_QUEUED") if terminal else "NOT_TERMINAL",
        "exit_code": terminal.get("exit") if terminal else None,
        "reason": terminal.get("reason", "") if terminal else "waiting",
        "evidence": list(terminal.get("evidence", [])) if terminal else [],
        "worktree": _Path.home()/f".local/state/conduvera/worktrees/{task_id}-{attempt_id}",
    }
    # Evidence state: also surface the real worktree artefacts (stdout/stderr).
    wt_dir = _Path.home()/f".local/state/conduvera/worktrees/{task_id}-{attempt_id}"
    if wt_dir.is_dir():
        art = sorted([p.name for p in wt_dir.glob("mxs_*") if p.suffix in (".txt", ".json")])
        if art:
            surface["evidence"] = surface["evidence"] + [str(wt_dir/a) for a in art]
    if json_output:
        typer.echo(json.dumps({"ok": True, "result": surface}, indent=2))
        return
    print("\n=== OPERATOR CONSOLE — local-first run ===")
    print(f"  goal            : {goal}")
    print(f"  job/attempt     : {job_id} / {attempt_id}")
    print(f"  harness/route   : {harness} -> {route}  (policy={policy})")
    print(f"  model identity  : {model_id}")
    print(f"  context         : served={served} verified={verified}")
    print(f"  gpu mode/res    : {gpu_mode} | {gpu}")
    print(f"  lifecycle       : {surface['lifecycle']}  exit={surface['exit_code']}  reason={surface['reason']}")
    print(f"  worktree        : {surface['worktree']}")
    if surface["evidence"]:
        print(f"  evidence        : {len(surface['evidence'])} artefact(s)")
        for e in surface["evidence"][:4]:
            print(f"                    {e}")
    else:
        print("  evidence        : (none yet)")


@control_app.command("list")
def list_sessions(json_output: bool = typer.Option(False, "--json", help="JSON output")) -> None:
    """List sessions and jobs."""
    _emit(_call("list"), json_output)


@control_app.command("console")
def console_view(
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
    limit: int = typer.Option(20, "--limit", help="max rows per section"),
) -> None:
    """Konsolidierte Operator-Console: queued / running / terminal.

    Nutzt NUR die reale Control-Plane-API (console endpoint) — kein Öffnen
    von State-Dateien. Zeigt payload_ref/hash, worktree/base, elapsed/deadline,
    terminal reason/exit und Evidence-Referenzen; NIE raw Prompts.
    """
    result = _call("console")
    if json_output or not result.get("ok"):
        _emit(result, json_output)
        return
    r = result.get("result", {})
    counts = r.get("counts", {})
    typer.echo(f"Operator Console — queued={counts.get('queued')} "
               f"running={counts.get('running')} terminal={counts.get('terminal')} "
               f"({r.get('server_time_utc','')})")

    q = r.get("queued", [])[:limit]
    if q:
        typer.echo("\n[QUEUED]")
        for a in q:
            typer.echo(f"  {a.get('job_id',''):20s} {a.get('task_id',''):18s} "
                       f"harness={a.get('harness',''):14s} type={a.get('task_type',''):12s} "
                       f"payload={a.get('payload_ref','')[:14]}")
            typer.echo(f"    base={a.get('base_commit','')[:10]} "
                       f"queued={a.get('elapsed_s')}s "
                       f"hash={str(a.get('content_sha256',''))[:16]}")

    rn = r.get("running", [])[:limit]
    if rn:
        typer.echo("\n[RUNNING]")
        for s in rn:
            typer.echo(f"  {s.get('session_id',''):20s} {s.get('task_id',''):18s} "
                       f"harness={s.get('harness',''):14s} elapsed={s.get('elapsed_s')}s")
            typer.echo(f"    scope={s.get('scope_id','')} pid={s.get('pid')}")
            typer.echo(f"    worktree={s.get('worktree','')}")
            typer.echo(f"    base={s.get('base_commit','')[:10]} "
                       f"deadline={s.get('deadline_utc','')}")

    t = r.get("terminal", [])[:limit]
    if t:
        typer.echo("\n[TERMINAL]")
        for j in t:
            typer.echo(f"  {j.get('job_id',''):20s} {j.get('task_id',''):18s} "
                       f"{j.get('state',''):12s} exit={j.get('exit_code')} "
                       f"reason={j.get('terminal_reason','')[:40]}")
            if j.get("result_refs"):
                typer.echo(f"    evidence={j['result_refs']}")
            typer.echo(f"    payload={j.get('payload_ref','')[:14]} "
                       f"hash={str(j.get('content_sha256',''))[:16]}")


@control_app.command("queue")
def queue_overview(
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Queue overview: attempts + jobs with lifecycle states."""
    result = _call("queue")
    if json_output or not result.get("ok"):
        _emit(result, json_output)
        return
    attempts = result.get("result", {}).get("attempts", [])
    jobs = result.get("result", {}).get("jobs", [])
    typer.echo(f"Queue: {len(attempts)} attempts, {len(jobs)} jobs")
    for a in sorted(attempts, key=lambda x: x.get("created_at", "")):
        typer.echo(f"  {a.get('attempt_id'):20s} {a.get('state'):12s} "
                   f"harness={a.get('harness',''):14s} terminal={a.get('terminal')}")
    for j in sorted(jobs, key=lambda x: x.get("created_at", ""))[-10:]:
        typer.echo(f"  Job {j.get('job_id'):20s} {j.get('state'):12s} "
                   f"task={j.get('task_id','')}")


@control_app.command("inspect")
def inspect(
    session_id: str = typer.Argument(..., help="session identifier"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Inspect/status a session."""
    result = _call("inspect", {"session_id": session_id})
    if json_output or not result.get("ok"):
        _emit(result, json_output)
        return
    r = result.get("result", {})
    typer.echo(f"Session {session_id}: {r.get('state')}")
    if r.get("pid"):
        typer.echo(f"  pid={r.get('pid')} scope={r.get('scope_id','')}")
    # elapsed time + deadline
    lst = _call("list")
    for s in lst.get("result", {}).get("sessions", []):
        if s.get("session_id") == session_id:
            import datetime as _dt
            st = s.get("started_at", "")
            if st:
                try:
                    started = _dt.datetime.fromisoformat(st)
                    elapsed = (_dt.datetime.now(_dt.timezone.utc) - started.replace(
                        tzinfo=_dt.timezone.utc)).total_seconds()
                    typer.echo(f"  elapsed={elapsed:.0f}s timeout={s.get('timeout_s')}s "
                               f"deadline={started.replace(tzinfo=_dt.timezone.utc) + _dt.timedelta(seconds=s.get('timeout_s', 0))}")
                except ValueError:
                    pass
            typer.echo(f"  worktree={s.get('worktree','')}")
            typer.echo(f"  base_commit={s.get('base_commit','')}")
            typer.echo(f"  harness={s.get('harness_descriptor','')} "
                       f"model={s.get('model_binding',{}).get('route','')}")
            break


@control_app.command("cancel")
def cancel(
    session_id: str = typer.Argument(..., help="session identifier"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Cancel a managed session."""
    _emit(_call("cancel", {"session_id": session_id}), json_output)


@control_app.command("cleanup")
def cleanup(
    session_id: str = typer.Argument(..., help="session identifier"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Clean up session-owned temporary resources."""
    _emit(_call("cleanup", {"session_id": session_id}), json_output)


@control_app.command("reconcile")
def reconcile(json_output: bool = typer.Option(False, "--json", help="JSON output")) -> None:
    """Reconcile registry with reality (restart-safe)."""
    _emit(_call("reconcile"), json_output)


@control_app.command("capabilities")
def capabilities(
    harness: str = typer.Argument("hermes_scoped", help="harness id"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Declared capabilities for a harness."""
    _emit(_call("capabilities", {"harness": harness}), json_output)


@control_app.command("logs")
def logs(
    session_id: str = typer.Argument(..., help="session identifier"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Show evidence/logs for a session (via collect_evidence)."""
    result = _call("inspect", {"session_id": session_id})
    _emit(result, json_output)


# ---- Delivery domain (SHIP-CONDUVERA-DELIVERY) ---------------------------

@control_app.command("delivery")
def delivery(
    subcommand: str = typer.Argument(..., help="inspect|preflight|publish|sync|list|cleanup|select-attempt|candidate-approve|candidate-list"),
    target: str = typer.Argument("", help="job-or-delivery identifier"),
    attempt_id: str = typer.Option("", "--attempt-id", help="explicit delivery-source Attempt"),
    candidate_id: str = typer.Option("", "--candidate-id", help="approved PublishCandidate id"),
    approved_by: str = typer.Option("operator", "--approved-by", help="candidate approver"),
    base_branch: str = typer.Option("main", "--base-branch", help="PR base branch"),
    safe_only: bool = typer.Option(True, "--safe-only/--no-safe-only",
                                   help="preserve worktree on unsafe delivery"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Delivery workspace: turn a completed job into a GitHub PR.

    Subcommands:
      inspect          <job-or-delivery>  show the DeliveryRecord + history
      preflight        <job-or-delivery>  run the fail-closed gate (+ candidate)
      publish          <job-or-delivery>  create task branch + one GitHub PR
      sync             <job-or-delivery>  refresh PR checks/reviews/mergeability
      list                                list all DeliveryRecords
      cleanup          <job-or-delivery>  remove disposable resources
      select-attempt   <job> <attempt-id> persist the delivery-source Attempt
      candidate-approve <candidate-id>    approve an immutable PublishCandidate
      candidate-list                       list PublishCandidates
    """
    if subcommand == "list":
        _emit(_call("delivery_list"), json_output)
        return
    if subcommand == "inspect":
        _emit(_call("delivery_inspect", {"delivery_id": target}), json_output)
        return
    if subcommand == "preflight":
        _emit(_call("delivery_preflight", {"job_or_delivery": target,
                                           "attempt_id": attempt_id or None}),
              json_output)
        return
    if subcommand == "publish":
        _emit(_call("delivery_publish", {"job_or_delivery": target,
                                         "base_branch": base_branch,
                                         "attempt_id": attempt_id or None,
                                         "candidate_id": candidate_id or None}),
              json_output)
        return
    if subcommand == "sync":
        _emit(_call("delivery_sync", {"job_or_delivery": target}), json_output)
        return
    if subcommand == "check-details":
        _emit(_call("delivery_check_details", {"job_or_delivery": target}),
              json_output)
        return
    if subcommand == "cleanup":
        _emit(_call("delivery_cleanup", {"job_or_delivery": target,
                                         "safe_only": safe_only}), json_output)
        return
    if subcommand == "select-attempt":
        if not target or not attempt_id:
            typer.echo("select-attempt requires <job> and --attempt-id", err=True)
            raise typer.Exit(2)
        _emit(_call("delivery_select_attempt", {"job_id": target,
                                                "attempt_id": attempt_id}),
              json_output)
        return
    if subcommand == "candidate-approve":
        if not candidate_id:
            typer.echo("candidate-approve requires --candidate-id", err=True)
            raise typer.Exit(2)
        _emit(_call("delivery_candidate_approve", {"candidate_id": candidate_id,
                                                   "approved_by": approved_by}),
              json_output)
        return
    if subcommand == "candidate-list":
        _emit(_call("delivery_candidate_list"), json_output)
        return
    typer.echo(f"unknown delivery subcommand: {subcommand}", err=True)
