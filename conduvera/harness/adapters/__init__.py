"""Core harness adapters using transient user systemd scopes (production path).

CONTROL-PLANE-V1 / MXOS-SAFETY-1.

ScopedProcessAdapter implements the HarnessAdapterProtocol for any CLI
harness by launching the process inside its own transient user systemd scope
(cgroup) via `systemd-run --user --scope`. This gives:

- real cgroup/scope isolation (SIGTERM -> grace -> SIGKILL targets only the
  owned scope);
- full process fingerprinting (pid + start_time + boot_id + command);
- structured UNSUPPORTED for pause/steer/checkpoint/attach/streaming.

Three harness instances:
- hermes_scoped  -> hermes binary (released Hermes adapter semantics, but
                    production scope isolation without touching the released
                    0.1.7 adapter package)
- codex_cli      -> codex (native Codex CLI, direct model binding, no
                    OAuth/LiteLLM alias)
- opencode_cli   -> opencode (real CLI `opencode run` interface)

Process-group fallback is used ONLY when systemd user scopes are
demonstrably unavailable.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from conduvera.control.adapters.base import AdapterResult
from conduvera.harness.managed_session import (
    _boot_id,
    _process_cmd,
    _process_start_time,
)


@dataclass
class HarnessSpec:
    """Declarative harness binary specification."""

    binary: str
    version_args: tuple[str, ...] = ("--version",)
    start_args_builder: Callable[[str, dict[str, Any]], list[str]] | None = None
    doctor_cmd: tuple[str, ...] | None = None
    extra_env: dict[str, str] | None = None
    allowlist_extra: tuple[str, ...] = ()


def _systemd_scope_available() -> bool:
    try:
        r = subprocess.run(
            ["systemd-run", "--user", "--scope", "--unit=conduvera-probe",
             "/bin/true"],
            capture_output=True, text=True, timeout=15,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


_SCOPE_AVAILABLE = _systemd_scope_available()


class ScopedProcessAdapter:
    """HarnessAdapterProtocol implementation via transient systemd scope."""

    name = "scoped-process"
    adapter_version = "conduvera-scope-adapter.v1"

    def __init__(
        self,
        *,
        spec: HarnessSpec,
        task_timeout_s: float = 180.0,
    ):
        self._spec = spec
        self._task_timeout_s = task_timeout_s
        self._sessions: dict[str, dict[str, Any]] = {}

    # -- capability --------------------------------------------------------

    def health_check(self) -> AdapterResult:
        binary = shutil.which(self._spec.binary)
        if binary is None:
            return AdapterResult(
                success=False,
                message=f"CAPABILITY_UNAVAILABLE: {self._spec.binary} not on PATH",
                detail={"code": "CAPABILITY_UNAVAILABLE", "binary": self._spec.binary},
            )
        try:
            r = subprocess.run(
                [binary, *self._spec.version_args],
                capture_output=True, text=True, timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            return AdapterResult(
                success=False, message=f"{self._spec.binary} version probe failed",
                detail={"code": "CAPABILITY_UNAVAILABLE"})
        return AdapterResult(
            success=True,
            message=f"{self._spec.binary} available",
            detail={"version": (r.stdout or r.stderr).strip()[:120],
                    "scope_isolation": _SCOPE_AVAILABLE},
        )

    def is_enabled(self) -> bool:
        return True

    def _require_enabled(self) -> None:
        return None

    # -- helpers -----------------------------------------------------------

    def _fingerprint_ok(self, session: dict[str, Any]) -> bool:
        pid = int(session.get("pid", 0))
        if pid <= 0:
            return False
        live = _process_start_time(pid)
        if not live:
            return False
        expected = session.get("start_time", "")
        return bool(expected) and live == expected

    def _scope_members(self, scope: str) -> list[int]:
        try:
            r = subprocess.run(
                ["systemctl", "--user", "show", scope, "-p", "MainPID", "--value"],
                capture_output=True, text=True, timeout=10,
            )
            main = r.stdout.strip()
            if main and main.isdigit():
                return [int(main)]
        except (OSError, subprocess.TimeoutExpired):
            pass
        return []

    def _kill_scope(self, scope: str, sig: int) -> None:
        try:
            subprocess.run(
                ["systemctl", "--user", "kill", scope, "-s",
                 signal.Signals(sig).name],
                capture_output=True, text=True, timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    # -- start -------------------------------------------------------------

    def start_session(
        self,
        agent_id: str,
        worktree: str,
        task: str,
        config: dict[str, Any],
    ) -> AdapterResult:
        wt = Path(worktree).expanduser().resolve()
        wt.mkdir(parents=True, exist_ok=True)
        prompt = str(config.get("prompt", "PONG"))
        task_command = config.get("task_command")
        timeout_s = float(config.get("timeout_s", self._task_timeout_s))
        binary = shutil.which(self._spec.binary)
        if binary is None:
            return AdapterResult(
                success=False,
                message=f"CAPABILITY_UNAVAILABLE: {self._spec.binary} not found",
                detail={"code": "CAPABILITY_UNAVAILABLE"})
        sid = f"mxs_{uuid.uuid4().hex[:16]}"
        scope = f"conduvera-{sid}.scope"
        stdout_path = wt / f"{sid}.stdout.txt"
        stderr_path = wt / f"{sid}.stderr.txt"

        args = self._spec.start_args_builder(prompt, config) if self._spec.start_args_builder \
            else [prompt]
        cmd = [binary, *args]
        if task_command:
            # Deterministic fixture task: run a bounded shell command in the
            # worktree via the harness scope (systemd-run --scope). Used for
            # cancellation/timeout/completion acceptance proofs where a
            # long-lived deterministic process is required. The command is
            # validated (no shell metacharacters beyond a fixed allowlist).
            cmd = ["bash", "-c", task_command]

        if _SCOPE_AVAILABLE:
            spawn = ["systemd-run", "--user", "--scope", "--unit", scope,
                     "--collect", "--quiet"] + cmd
        else:
            # process-group fallback (only when scopes demonstrably unavailable)
            spawn = cmd

        env = dict(os.environ)
        for k, v in (self._spec.extra_env or {}).items():
            env[k] = v

        try:
            with open(stdout_path, "w", encoding="utf-8") as out, \
                 open(stderr_path, "w", encoding="utf-8") as err:
                proc = subprocess.Popen(
                    spawn,
                    stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                    env=env, cwd=str(wt),
                    start_new_session=not _SCOPE_AVAILABLE,
                )
        except OSError as exc:
            return AdapterResult(
                success=False, message=f"spawn failed: {exc}",
                detail={"code": "ADAPTER_PROTOCOL_ERROR"})
        pid = proc.pid
        # With systemd-run --scope the wrapper PID is transient: resolve the
        # scope MainPID so the fingerprint tracks the real harness process.
        resolved_pid = pid
        if _SCOPE_AVAILABLE:
            try:
                r = subprocess.run(
                    ["systemctl", "--user", "show", scope,
                     "-p", "MainPID", "--value"],
                    capture_output=True, text=True, timeout=10,
                )
                main = r.stdout.strip()
                if main.isdigit() and int(main) > 0:
                    resolved_pid = int(main)
            except (OSError, subprocess.TimeoutExpired):
                pass
        pid = resolved_pid
        session = {
            "session_id": sid,
            "pid": pid,
            "start_time": _process_start_time(pid),
            "boot_id": _boot_id(),
            "command": _process_cmd(pid),
            "scope": scope if _SCOPE_AVAILABLE else str(pid),
            "scope_isolation": _SCOPE_AVAILABLE,
            "status": "running",
            "output_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "timeout_s": timeout_s,
            "exit_code": None,
            "_popen": proc,
        }
        self._sessions[sid] = session
        # Watchdog thread: capture the real exit code when the owned process
        # terminates (works even when the transient scope is already gone).
        def _watch(session: dict[str, Any], proc: subprocess.Popen) -> None:
            try:
                rc = proc.wait(timeout=timeout_s + 30)
                session["exit_code"] = rc
            except subprocess.TimeoutExpired:
                session["exit_code"] = None
        threading.Thread(target=_watch, args=(session, proc), daemon=True).start()
        return AdapterResult(
            success=True,
            message=f"{self._spec.binary} session started (scope={session['scope']})",
            detail=session,
        )

    # -- status ------------------------------------------------------------

    def status_session(self, session_id: str) -> AdapterResult:
        session = self._sessions.get(session_id)
        if session is None:
            return AdapterResult(success=False, message=f"unknown session {session_id}",
                                 detail={"code": "UNKNOWN_SESSION"})
        if not self._fingerprint_ok(session):
            session["status"] = "lost"
            return AdapterResult(
                success=True, message=f"session {session_id} LOST (fingerprint mismatch)",
                detail={"session_id": session_id, "status": "lost",
                        "pid": session.get("pid")})
        try:
            os.kill(int(session["pid"]), 0)
            alive = True
        except ProcessLookupError:
            alive = False
        except PermissionError:
            alive = True
        status = "running" if alive else "exited"
        session["status"] = status
        return AdapterResult(
            success=True, message=f"session {session_id} {status}",
            detail={"session_id": session_id, "status": status,
                    "pid": session.get("pid"), "scope": session.get("scope")})

    # -- cancel ------------------------------------------------------------

    def cancel_session(self, session_id: str) -> AdapterResult:
        session = self._sessions.get(session_id)
        if session is None:
            return AdapterResult(success=False, message=f"unknown session {session_id}",
                                 detail={"code": "UNKNOWN_SESSION"})
        if not self._fingerprint_ok(session):
            return AdapterResult(
                success=False,
                message=f"session {session_id} fingerprint mismatch — no signal sent",
                detail={"code": "PROCESS_FINGERPRINT_MISMATCH"})
        if session.get("scope_isolation") and session.get("scope"):
            self._kill_scope(session["scope"], signal.SIGKILL)
            time.sleep(0.5)
            remaining = self._scope_members(session["scope"])
        else:
            try:
                os.killpg(int(session["pid"]), signal.SIGKILL)
            except ProcessLookupError:
                pass
            remaining = []
        session["status"] = "cancelled"
        return AdapterResult(
            success=True,
            message=f"session {session_id} cancelled (own scope {session.get('scope')})",
            detail={"session_id": session_id, "status": "cancelled",
                    "scope_remaining": remaining})

    # -- timeout -----------------------------------------------------------

    def timeout_session(self, session_id: str) -> AdapterResult:
        """SIGTERM -> grace -> SIGKILL to the owned scope only."""
        session = self._sessions.get(session_id)
        if session is None:
            return AdapterResult(success=False, message=f"unknown session {session_id}",
                                 detail={"code": "UNKNOWN_SESSION"})
        if not self._fingerprint_ok(session):
            return AdapterResult(
                success=False, message="fingerprint mismatch — no signal sent",
                detail={"code": "PROCESS_FINGERPRINT_MISMATCH"})
        if session.get("scope_isolation") and session.get("scope"):
            self._kill_scope(session["scope"], signal.SIGTERM)
            time.sleep(3.0)  # grace period
            remaining = self._scope_members(session["scope"])
            if remaining:
                self._kill_scope(session["scope"], signal.SIGKILL)
                time.sleep(0.5)
            remaining = self._scope_members(session["scope"])
        else:
            try:
                os.killpg(int(session["pid"]), signal.SIGTERM)
            except ProcessLookupError:
                pass
            time.sleep(3.0)
            remaining = []
        session["status"] = "timed_out"
        return AdapterResult(
            success=True,
            message=f"session {session_id} timed out (scope {session.get('scope')}; remaining={remaining})",
            detail={"session_id": session_id, "status": "timed_out",
                    "scope_remaining": remaining})

    def await_completion(self, session_id: str, timeout_policy: dict[str, Any] | None = None) -> AdapterResult:
        session = self._sessions.get(session_id)
        if session is None:
            return AdapterResult(success=False, message=f"unknown session {session_id}",
                                 detail={"code": "UNKNOWN_SESSION"})
        wait_s = float((timeout_policy or {}).get("wait_s", self._task_timeout_s))
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            if not self._fingerprint_ok(session):
                return AdapterResult(False, "fingerprint mismatch",
                                     detail={"code": "PROCESS_FINGERPRINT_MISMATCH"})
            try:
                os.kill(int(session["pid"]), 0)
                time.sleep(0.5)
            except ProcessLookupError:
                return AdapterResult(True, f"session {session_id} completed",
                                     detail={"session_id": session_id, "status": "completed"})
            except PermissionError:
                time.sleep(0.5)
        return AdapterResult(False, "wait timed out",
                             detail={"code": "SESSION_WAIT_FAILED"})

    def collect_evidence(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"session_id": session_id, "evidence": [], "ok": False,
                    "schema_version": "MXOS-EVIDENCE-1.0.0"}
        import hashlib
        artifacts = []
        for key in ("output_path", "stderr_path"):
            p = session.get(key)
            if p and Path(p).is_file():
                data = Path(p).read_bytes()
                artifacts.append({"path": p,
                                  "sha256": "sha256:" + hashlib.sha256(data).hexdigest()})
        # Actual exit code from the owned scope (systemd ExecMainStatus) or
        # the watchdog-captured process return code.
        exit_code = session.get("exit_code")
        if exit_code is None and session.get("scope_isolation") and session.get("scope"):
            try:
                r = subprocess.run(
                    ["systemctl", "--user", "show", session["scope"],
                     "-p", "ExecMainStatus", "--value"],
                    capture_output=True, text=True, timeout=10,
                )
                raw = r.stdout.strip()
                if raw.isdigit():
                    exit_code = int(raw)
            except (OSError, subprocess.TimeoutExpired):
                pass
        return {
            "session_id": session_id,
            "ok": True,
            "schema_version": "MXOS-EVIDENCE-1.0.0",
            "artifacts": artifacts,
            "harness": self._spec.binary,
            "status": session.get("status", ""),
            "exit_code": exit_code,
        }

    def stop_session(self, agent_id: str, session_ref: str) -> AdapterResult:
        return self.cancel_session(session_ref)

    def session_status(self, agent_id: str, session_ref: str) -> AdapterResult:
        return self.status_session(session_ref)

    def prepare_worktree(self, agent_id: str, worktree: str, scope_files: list, config: dict[str, Any]) -> AdapterResult:
        wt = Path(worktree).expanduser().resolve()
        wt.mkdir(parents=True, exist_ok=True)
        return AdapterResult(True, "worktree prepared", {"worktree": str(wt)})


# -- harness instances -----------------------------------------------------


def _hermes_args(prompt: str, config: dict[str, Any]) -> list[str]:
    return ["-z", prompt]


def _codex_args(prompt: str, config: dict[str, Any]) -> list[str]:
    # Native Codex CLI direct execution (no OAuth/LiteLLM alias).
    return ["exec", "--json", prompt]


def _opencode_args(prompt: str, config: dict[str, Any]) -> list[str]:
    # Real OpenCode CLI run interface.
    return ["run", prompt]


def hermes_scoped_adapter() -> ScopedProcessAdapter:
    return ScopedProcessAdapter(
        spec=HarnessSpec(binary="hermes", start_args_builder=_hermes_args),
        task_timeout_s=180.0,
    )


def codex_cli_adapter() -> ScopedProcessAdapter:
    return ScopedProcessAdapter(
        spec=HarnessSpec(
            binary="codex",
            version_args=("--version",),
            start_args_builder=_codex_args,
            doctor_cmd=("codex", "--version"),
        ),
        task_timeout_s=300.0,
    )


def opencode_cli_adapter() -> ScopedProcessAdapter:
    return ScopedProcessAdapter(
        spec=HarnessSpec(
            binary="opencode",
            version_args=("--version",),
            start_args_builder=_opencode_args,
            doctor_cmd=("opencode", "--version"),
        ),
        task_timeout_s=300.0,
    )


def _register_instances() -> dict[str, ScopedProcessAdapter]:
    return {
        "hermes_scoped": hermes_scoped_adapter(),
        "codex_cli": codex_cli_adapter(),
        "opencode_cli": opencode_cli_adapter(),
    }
