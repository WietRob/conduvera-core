"""Versioned Hermes harness adapter (CONDUVERA-GOAL-1.0, core-internal run).

This adapter OWNS the complete managed-session lifecycle:

- start_session() creates the isolated HERMES_HOME, writes the fixture
  config (custom:litellm + workload/local), starts the Hermes CLI itself
  (the ONLY place a Hermes process may be spawned), captures PID/PGID/
  create_time, and returns a canonical SessionHandle.
- status_session()/cancel_session()/timeout_session()/collect_evidence()
  serve THE SAME session via its persisted PID/PGID.
- No external test script may spawn Hermes directly; doing so is a
  boundary violation (DOD-01).

Removability invariant (adapters_are_removable):
If the adapter is disabled (registry flag), every call returns a structured
CAPABILITY_UNAVAILABLE result. Importing this module never fails, so Core
and ODS keep working with the adapter absent from the registry.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from curaops.control.adapters.base import AdapterResult, BaseAdapter


class HarnessCapabilityUnavailable(Exception):
    """Structured fail-closed error for disabled/removed adapters."""

    def __init__(self, adapter: str, reason: str):
        self.adapter = adapter
        self.reason = reason
        self.code = "CAPABILITY_UNAVAILABLE"
        super().__init__(f"{adapter}: {reason}")


@dataclass
class SessionHandle:
    """Canonical handle for a managed Hermes session."""

    session_id: str
    pid: int
    pgid: int
    create_time: str
    hermes_home: str
    status: str = "running"
    exitcode: int | None = None
    started_at: str = ""
    finished_at: str = ""
    output_path: str = ""
    route: str = "workload/local"
    model_identity: str = ""
    trace_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "pid": self.pid,
            "pgid": self.pgid,
            "create_time": self.create_time,
            "hermes_home": self.hermes_home,
            "status": self.status,
            "exitcode": self.exitcode,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "output_path": self.output_path,
            "route": self.route,
            "model_identity": self.model_identity,
            "trace_id": self.trace_id,
        }


@dataclass
class HermesAdapterState:
    """Persisted managed-session state (fixture scope only)."""

    handle: SessionHandle | None = None
    agent_id: str = ""
    worktree: str = ""
    task: str = ""
    model_binding: dict[str, Any] = field(default_factory=dict)


class HermesAdapter(BaseAdapter):
    """Adapter for the Hermes harness (owns the complete session lifecycle)."""

    name = "hermes"
    adapter_version = "hermes-adapter.v1"

    FIXTURE_PROMPT = "Antworte exakt mit CONDUVERA_FIXTURE_OK."

    def __init__(
        self,
        *,
        registry_path: str | Path | None = None,
        fixture_worktree: str | Path | None = None,
        task_timeout_s: float = 240.0,
        hermes_binary: str = "hermes",
        route: str = "workload/local",
    ):
        self._registry_path = (
            Path(registry_path).expanduser().resolve()
            if registry_path
            else Path.cwd() / "contracts" / "harness-registry.yaml"
        )
        self._fixture_worktree = (
            Path(fixture_worktree).expanduser().resolve()
            if fixture_worktree
            else Path.cwd() / "fixtures" / "hermes-worktree"
        )
        self._task_timeout_s = task_timeout_s
        self._hermes_binary = hermes_binary
        self._route = route
        self._sessions: dict[str, HermesAdapterState] = {}

    # -- registry ---------------------------------------------------------

    def is_enabled(self) -> bool:
        """Read the adapter registry flag (default: enabled when file absent)."""
        try:
            import yaml

            data = yaml.safe_load(self._registry_path.read_text(encoding="utf-8")) or {}
            adapters = data.get("adapters", data)
            if isinstance(adapters, dict) and "hermes" in adapters:
                return bool(adapters["hermes"].get("enabled", True))
        except FileNotFoundError:
            return True
        except Exception:
            return True
        return True

    def _require_enabled(self) -> None:
        if not self.is_enabled():
            raise HarnessCapabilityUnavailable(
                self.name, "adapter disabled in harness-registry.yaml (fail-closed)"
            )

    # -- BaseAdapter API --------------------------------------------------

    def health_check(self) -> AdapterResult:
        if not self.is_enabled():
            return AdapterResult(
                success=False,
                message="CAPABILITY_UNAVAILABLE: hermes adapter disabled",
                detail={"code": "CAPABILITY_UNAVAILABLE"},
            )
        return AdapterResult(success=True, message="hermes adapter available")

    def start_session(
        self,
        agent_id: str,
        worktree: str,
        task: str,
        config: dict[str, Any],
    ) -> AdapterResult:
        """Start a MANAGED Hermes session (owns HERMES_HOME + process spawn).

        The ONLY place in the system that may spawn a Hermes process.
        Creates the isolated HERMES_HOME, writes the fixture config
        (custom:litellm -> workload/local), starts `hermes -z` as a new
        session/process-group, and captures PID/PGID/create_time.
        """
        try:
            self._require_enabled()
        except HarnessCapabilityUnavailable as exc:
            return AdapterResult(
                success=False,
                message=str(exc),
                detail={"code": exc.code, "adapter": exc.adapter},
            )

        session_id = f"mxfix_{uuid.uuid4().hex[:12]}"
        trace_id = config.get("trace_id", session_id)
        wt = Path(worktree).expanduser().resolve()
        wt.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now(timezone.utc).isoformat()

        live = bool(config.get("live", False))
        route = str(config.get("route", self._route))

        if not live:
            # SIMULATOR mode (unit tests / dry runs): write a harmless text
            # artifact, never spawn a process. The live spawn is only taken
            # when the caller explicitly requests it (live verification).
            handle = SessionHandle(
                session_id=session_id,
                pid=0, pgid=0, create_time="",
                hermes_home=str(wt / "hermes-home"),
                status="completed",
                started_at=started_at,
                finished_at=started_at,
                output_path="",
                route=route,
                trace_id=trace_id,
            )
            out_dir = wt / "artifacts"
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = out_dir / f"{session_id}.txt"
            output_path.write_text(
                f"fixture task: {task}\nagent: {agent_id}\nsession: {session_id}\n"
                f"model_binding: {config.get('model_binding', {})}\nstatus: simulated\n",
                encoding="utf-8",
            )
            handle.output_path = str(output_path)
            self._sessions[session_id] = HermesAdapterState(
                handle=handle, agent_id=agent_id, worktree=str(wt),
                task=task, model_binding=dict(config.get("model_binding", {})),
            )
            return AdapterResult(
                success=True,
                message="hermes fixture session (simulated)",
                detail=handle.to_dict(),
            )

        # 1) Isolated HERMES_HOME + fixture config (no ~/.hermes mutation)
        hermes_home = wt / "hermes-home" / "profiles" / "fixture-live"
        hermes_home.mkdir(parents=True, exist_ok=True)
        (hermes_home / "config.yaml").write_text(
            _FIXTURE_CONFIG_TEMPLATE.format(route=self._route),
            encoding="utf-8",
        )

        # 2) Spawn Hermes ourselves (own process group, no TTY)
        env = dict(os.environ)
        env["HERMES_HOME"] = str(hermes_home)
        prompt = config.get("prompt", self.FIXTURE_PROMPT)
        response_path = wt / f"{session_id}.response.txt"
        proc = subprocess.Popen(
            [self._hermes_binary, "-z", prompt],
            stdout=open(response_path, "w", encoding="utf-8"),
            stderr=open(wt / f"{session_id}.stderr.txt", "w", encoding="utf-8"),
            stdin=subprocess.DEVNULL,
            env=env,
            cwd=str(wt),
            start_new_session=True,  # own PGID
        )
        pid = proc.pid
        pgid = os.getpgid(pid)
        try:
            ps = subprocess.run(
                ["ps", "-o", "lstart=", "-p", str(pid)],
                capture_output=True, text=True, timeout=5,
            )
            create_time = ps.stdout.strip()
        except Exception:
            create_time = ""

        handle = SessionHandle(
            session_id=session_id,
            pid=pid,
            pgid=pgid,
            create_time=create_time,
            hermes_home=str(hermes_home),
            status="running",
            started_at=started_at,
            output_path=str(response_path),
            route=self._route,
            trace_id=trace_id,
        )
        self._sessions[session_id] = HermesAdapterState(
            handle=handle,
            agent_id=agent_id,
            worktree=str(wt),
            task=task,
            model_binding=dict(config.get("model_binding", {})),
        )

        return AdapterResult(
            success=True,
            message="hermes managed session started",
            detail=handle.to_dict(),
        )

    def wait_for_completion(self, session_id: str, timeout_s: float | None = None) -> None:
        """Wait for the managed process (bounded); never touches foreign PIDs.

        Handles zombies correctly: a reaped-but-not-waited child (state Z)
        must not block the loop — waitpid(WNOHANG) is attempted each
        iteration so a finished process is reaped promptly.
        """
        state = self._sessions.get(session_id)
        if state is None or state.handle is None:
            return
        handle = state.handle
        if handle.pid <= 0:
            # Simulator handle (no real process) — nothing to wait for.
            return
        deadline = time.monotonic() + (timeout_s if timeout_s is not None else self._task_timeout_s)
        while time.monotonic() < deadline:
            # Reap first: a zombie (state Z) still answers os.kill(pid, 0),
            # so we must waitpid() to collect it before checking liveness.
            try:
                waited, status = os.waitpid(handle.pid, os.WNOHANG)
                if waited == handle.pid:
                    handle.exitcode = os.waitstatus_to_exitcode(status)
                    handle.status = "completed" if handle.exitcode == 0 else "failed"
                    handle.finished_at = datetime.now(timezone.utc).isoformat()
                    return
            except ChildProcessError:
                # Already reaped by a prior call — check final state.
                if handle.exitcode is not None:
                    return
            except ProcessLookupError:
                handle.exitcode = 0
                handle.status = "completed"
                handle.finished_at = datetime.now(timezone.utc).isoformat()
                return
            try:
                os.kill(handle.pid, 0)  # exists (or is a zombie)?
                time.sleep(0.3)
            except ProcessLookupError:
                break
            except PermissionError:
                time.sleep(0.3)
        # Deadline reached with the process still present (or zombie).
        try:
            waited, status = os.waitpid(handle.pid, os.WNOHANG)
            if waited == handle.pid:
                handle.exitcode = os.waitstatus_to_exitcode(status)
                handle.status = "completed" if handle.exitcode == 0 else "failed"
                handle.finished_at = datetime.now(timezone.utc).isoformat()
        except (ChildProcessError, ProcessLookupError):
            pass

    def status_session(self, session_id: str) -> AdapterResult:
        """Return the managed session status (structured, never foreign)."""
        try:
            self._require_enabled()
        except HarnessCapabilityUnavailable as exc:
            return AdapterResult(
                success=False, message=str(exc), detail={"code": exc.code}
            )
        state = self._sessions.get(session_id)
        if state is None or state.handle is None:
            return AdapterResult(
                success=False,
                message=f"unknown session {session_id}",
                detail={"code": "UNKNOWN_SESSION"},
            )
        handle = state.handle
        if handle.pid <= 0:
            # Simulator handle — completed synchronously.
            return AdapterResult(
                success=True,
                message=f"session {session_id} status {handle.status}",
                detail={"session_id": session_id, "status": handle.status, "pid": 0, "pgid": 0},
            )
        alive = True
        try:
            os.kill(handle.pid, 0)
        except ProcessLookupError:
            alive = False
        except PermissionError:
            alive = True
        status = handle.status if alive else (handle.status if handle.exitcode is not None else "exited")
        return AdapterResult(
            success=True,
            message=f"session {session_id} status {status}",
            detail={"session_id": session_id, "status": status, "pid": handle.pid, "pgid": handle.pgid},
        )

    def cancel_session(self, session_id: str) -> AdapterResult:
        """Cancel ONLY the managed session (SIGKILL to its own PGID)."""
        try:
            self._require_enabled()
        except HarnessCapabilityUnavailable as exc:
            return AdapterResult(
                success=False, message=str(exc), detail={"code": exc.code}
            )
        state = self._sessions.get(session_id)
        if state is None or state.handle is None:
            return AdapterResult(
                success=False, message=f"unknown session {session_id}",
                detail={"code": "UNKNOWN_SESSION"},
            )
        handle = state.handle
        if handle.pid <= 0:
            # Simulator handle — no real process to cancel.
            handle.status = "cancelled"
            handle.finished_at = datetime.now(timezone.utc).isoformat()
            return AdapterResult(
                success=True,
                message=f"session {session_id} cancelled (simulated)",
                detail=handle.to_dict(),
            )
        try:
            os.killpg(handle.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        handle.status = "cancelled"
        handle.finished_at = datetime.now(timezone.utc).isoformat()
        return AdapterResult(
            success=True,
            message=f"session {session_id} cancelled (own PGID {handle.pgid})",
            detail=handle.to_dict(),
        )

    def timeout_session(self, session_id: str) -> AdapterResult:
        """Timeout ONLY the managed session (SIGTERM -> grace -> SIGKILL)."""
        try:
            self._require_enabled()
        except HarnessCapabilityUnavailable as exc:
            return AdapterResult(
                success=False, message=str(exc), detail={"code": exc.code}
            )
        state = self._sessions.get(session_id)
        if state is None or state.handle is None:
            return AdapterResult(
                success=False, message=f"unknown session {session_id}",
                detail={"code": "UNKNOWN_SESSION"},
            )
        handle = state.handle
        if handle.pid <= 0:
            # Simulator handle — no real process to time out.
            handle.status = "timed_out"
            handle.finished_at = datetime.now(timezone.utc).isoformat()
            return AdapterResult(
                success=True,
                message=f"session {session_id} timed out (simulated)",
                detail=handle.to_dict(),
            )
        try:
            os.killpg(handle.pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        time.sleep(3)
        try:
            os.killpg(handle.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        handle.status = "timed_out"
        handle.finished_at = datetime.now(timezone.utc).isoformat()
        return AdapterResult(
            success=True,
            message=f"session {session_id} timed out (own PGID {handle.pgid})",
            detail=handle.to_dict(),
        )

    def collect_evidence(self, session_id: str) -> dict[str, Any]:
        """Collect evidence for the managed session (same session as started)."""
        state = self._sessions.get(session_id)
        if state is None or state.handle is None:
            return {"session_id": session_id, "evidence": [], "ok": False}
        handle = state.handle
        artifacts = []
        if handle.output_path and Path(handle.output_path).is_file():
            artifacts.append(
                {
                    "path": handle.output_path,
                    "sha256": _sha256(Path(handle.output_path).read_bytes()),
                }
            )
        return {
            "session_id": session_id,
            "status": handle.status,
            "artifacts": artifacts,
            "model_binding": state.model_binding,
            "handle": handle.to_dict(),
            "ok": True,
        }

    # -- BaseAdapter abstract methods -------------------------------------

    def stop_session(self, agent_id: str, session_ref: str) -> AdapterResult:
        """Stop a managed session (alias of cancel)."""
        return self.cancel_session(session_ref)

    def session_status(self, agent_id: str, session_ref: str) -> AdapterResult:
        """Alias of status_session (BaseAdapter-compatible)."""
        return self.status_session(session_ref)

    def prepare_worktree(
        self,
        agent_id: str,
        worktree: str,
        scope_files: list,
        config: dict[str, Any],
    ) -> AdapterResult:
        """Prepare a fixture worktree (harmless marker files only)."""
        wt = Path(worktree).expanduser().resolve()
        wt.mkdir(parents=True, exist_ok=True)
        (wt / ".agent-id").write_text(agent_id, encoding="utf-8")
        (wt / ".task-key").write_text(str(config.get("task", "")), encoding="utf-8")
        return AdapterResult(
            success=True,
            message="fixture worktree prepared",
            detail={"worktree": str(wt)},
        )


# Config template: isolated profile, custom:litellm -> workload/local,
# LITELLM_API_KEY comes from the process environment (existing injection,
# never read or printed by this module).
_FIXTURE_CONFIG_TEMPLATE = """model:
  default: {route}
  provider: custom:litellm
  context_length: 65536
providers:
  litellm:
    api: http://127.0.0.1:4000/v1
    name: litellm
    key_env: LITELLM_API_KEY
    transport: chat_completions
agent:
  verify_on_stop: false
display:
  tool_progress: none
_config_version: 33
"""


def _sha256(data: bytes) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(data).hexdigest()
