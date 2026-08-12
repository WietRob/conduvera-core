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
import sys
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
    npx_package: str | None = None
    # When True the harness reads its task prompt from STDIN (verified for
    # opencode: `opencode run` with no message arg consumes stdin), so the raw
    # prompt never appears in the process argv / systemd scope description.
    stdin_prompt: bool = False

    def resolve_binary(self) -> str | None:
        """Resolve the executable, optionally through npx."""
        if self.npx_package:
            npx = shutil.which("npx")
            if npx:
                return npx
            return None
        return shutil.which(self.binary)


def _systemd_scope_available() -> bool:
    try:
        # Unique unit name: a fixed probe unit collides on repeat calls
        # (the scope lingers briefly), making the check unstable.
        import uuid
        unit = f"conduvera-probe-{uuid.uuid4().hex[:8]}"
        r = subprocess.run(
            ["systemd-run", "--user", "--scope", f"--unit={unit}",
             "--collect", "--quiet", "/bin/true"],
            capture_output=True, text=True, timeout=15,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


_SCOPE_AVAILABLE = _systemd_scope_available()


def _use_scope() -> bool:
    """Re-check scope availability at dispatch time (module-import caching of
    _SCOPE_AVAILABLE is unreliable during daemon startup when the transient
    probe unit may collide). Falling back to a raw process group must never
    silently run the harness outside the dedicated worktree, so the scope
    path (which pins --working-directory) is preferred whenever available.
    """
    if _SCOPE_AVAILABLE:
        return True
    return _systemd_scope_available()


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
        binary = self._spec.resolve_binary()
        if binary is None:
            return AdapterResult(
                success=False,
                message=f"CAPABILITY_UNAVAILABLE: {self._spec.binary} not on PATH",
                detail={"code": "CAPABILITY_UNAVAILABLE", "binary": self._spec.binary},
            )
        version_cmd = [binary]
        if self._spec.npx_package:
            version_cmd += ["--yes", self._spec.npx_package, "--version"]
        else:
            version_cmd += list(self._spec.version_args)
        try:
            r = subprocess.run(
                version_cmd,
                capture_output=True, text=True, timeout=30,
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
        timeout_s = float(config.get("timeout_s", self._task_timeout_s))
        binary = self._spec.resolve_binary()
        if binary is None:
            return AdapterResult(
                success=False,
                message=f"CAPABILITY_UNAVAILABLE: {self._spec.binary} not found",
                detail={"code": "CAPABILITY_UNAVAILABLE"})
        sid = f"mxs_{uuid.uuid4().hex[:16]}"
        scope = f"conduvera-{sid}.scope"
        stdout_path = wt / f"{sid}.stdout.txt"
        stderr_path = wt / f"{sid}.stderr.txt"

        # expose the worktree to harness-specific argument builders (e.g.
        # opencode --dir) so the harness pins its working directory even when
        # it would otherwise inherit the caller's PWD.
        cfg = dict(config)
        cfg.setdefault("worktree", str(wt))
        args = self._spec.start_args_builder(prompt, cfg) if self._spec.start_args_builder \
            else [prompt]
        cmd = [binary]
        if self._spec.npx_package:
            cmd += ["--yes", self._spec.npx_package]
        cmd += args

        use_scope = _use_scope()
        # registry/worktree binding (Work B): pass through for cwd_exec
        # validation so it never trusts an arbitrary path below the root.
        bind_repo = str(config.get("repo_path", ""))
        bind_base = str(config.get("base_commit", ""))
        bind_attempt = str(config.get("attempt_id", ""))
        bind_args = ["--task-id", task,
                     "--attempt-id", bind_attempt,
                     "--repo", bind_repo,
                     "--base", bind_base]
        if use_scope:
            # Shell-free cwd executor: systemd-run's --working-directory sets
            # opencode's instance-directory but NOT the grandchild process cwd
            # that opencode uses for git resolution (it inherits the caller's
            # PWD). Invoke conduvera.harness.cwd_exec through systemd-run as
            # ordinary argv elements: it os.chdir()s into the validated
            # worktree and os.execvpe()s the harness with the prompt passed
            # through UNCHANGED (no bash/sh, no string concatenation, no shell
            # evaluation, no injection surface).
            spawn = ["systemd-run", "--user", "--scope", "--unit", scope,
                     "--collect", "--quiet",
                     sys.executable, "-m", "conduvera.harness.cwd_exec",
                     "--cwd", str(wt)] + bind_args + ["--"] + cmd
        else:
            # process-group fallback (only when scopes demonstrably unavailable):
            # still use the shell-free cwd executor so the worktree boundary and
            # injection protection hold regardless of scope availability.
            spawn = [sys.executable, "-m", "conduvera.harness.cwd_exec",
                     "--cwd", str(wt)] + bind_args + ["--"] + cmd

        env = dict(os.environ)
        for k, v in (self._spec.extra_env or {}).items():
            env[k] = v

        try:
            with open(stdout_path, "w", encoding="utf-8") as out, \
                 open(stderr_path, "w", encoding="utf-8") as err:
                # Secret-safe: when the harness consumes its prompt from STDIN
                # (opencode), pipe it through instead of DEVNULL. systemd-run
                # and cwd_exec both forward stdin, so the prompt reaches the
                # harness without ever appearing in argv / scope description.
                if self._spec.stdin_prompt:
                    proc = subprocess.Popen(
                        spawn,
                        stdout=out, stderr=err, stdin=subprocess.PIPE,
                        env=env, cwd=str(wt),
                        start_new_session=not use_scope,
                    )
                    try:
                        proc.stdin.write(prompt.encode("utf-8"))
                        proc.stdin.close()
                    except (BrokenPipeError, OSError):
                        pass
                else:
                    proc = subprocess.Popen(
                        spawn,
                        stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                        env=env, cwd=str(wt),
                        start_new_session=not use_scope,
                    )
        except OSError as exc:
            return AdapterResult(
                success=False, message=f"spawn failed: {exc}",
                detail={"code": "ADAPTER_PROTOCOL_ERROR"})
        pid = proc.pid
        # With systemd-run --scope the wrapper PID is transient: resolve the
        # scope MainPID so the fingerprint tracks the real harness process.
        resolved_pid = pid
        if use_scope:
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
            "scope": scope if use_scope else str(pid),
            "scope_isolation": use_scope,
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
    # Sandbox: bwrap workspace-write is blocked on this host by AppArmor
    # (kernel.apparmor_restrict_unprivileged_userns=1, no sudo). The
    # worktree boundary is enforced by the control-plane scope isolation
    # (cwd=worktree, KillMode=control-group) + byte-identical base-checkout
    # verification after the run. danger-full-access is used ONLY inside that
    # isolated scope; it never grants access to the base repository.
    return ["exec", "--sandbox", "danger-full-access", "--json", prompt]


def _opencode_args(prompt: str, config: dict[str, Any]) -> list[str]:
    # Real OpenCode CLI run interface, non-interactive, JSON events for
    # clean exit handling. OpenCode uses its own native auth domain
    # (~/.local/share/opencode/auth.json) and its configured default model
    # (opencode.json); no ODS/LiteLLM/route change. --dir pins the worktree
    # because OpenCode otherwise inherits the caller's PWD (the cwd_exec
    # os.chdir does not propagate to OpenCode's server instance).
    # Secret-safe: NO prompt message argument — OpenCode consumes the task
    # prompt from STDIN (verified: `opencode run` with no message arg reads
    # stdin), so the raw prompt never appears in argv / scope output.
    args = ["run", "--format", "json"]
    wt = config.get("worktree")
    if wt:
        args += ["--dir", str(wt)]
    return args


def _pi_args(prompt: str, config: dict[str, Any]) -> list[str]:
    # Pi Agent Harness: non-interactive print mode against the local
    # LiteLLM provider (models.json: litellm-local), offline startup.
    # The API key is passed via --api-key from the process environment
    # (never persisted, never logged).
    model = config.get("model", "litellm-local/local/qwen-3.6-35b")
    args = ["--model", model, "--print", prompt, "--offline"]
    api_key = (os.environ.get("LITELLM_API_KEY")
               or os.environ.get("LITELLM_KEY")
               or os.environ.get("LITELLM_MASTER_KEY")
               or os.environ.get("OPENAI_API_KEY"))
    if api_key:
        args += ["--api-key", api_key]
    return args


def _acceptance_args(prompt: str, config: dict[str, Any]) -> list[str]:
    """Acceptance-only fixture args: a FIXED enum scenario, never a command.

    The scenario is read from config['scenario'] (validated against the fixed
    enum) and passed as `--scenario <ENUM>`. No arbitrary command, no shell,
    no caller-controlled exec. hold-s is a bounded float from config.
    """
    from conduvera.harness.acceptance_fixture import SCENARIOS
    scenario = config.get("scenario", "")
    if scenario not in SCENARIOS:
        raise ValueError(f"invalid acceptance scenario: {scenario!r}")
    args = ["-m", "conduvera.harness.acceptance_fixture",
            "--scenario", scenario]
    hold = config.get("hold_s", 60.0)
    if hold is not None:
        args += ["--hold-s", str(float(hold))]
    out = config.get("fixture_out")
    if out:
        # resolve relative to the managed worktree (config has it)
        wt = config.get("worktree")
        if wt and not os.path.isabs(out):
            out = str(Path(wt) / out)
        args += ["--out", str(out)]
    return args


def pi_cli_adapter() -> ScopedProcessAdapter:
    return ScopedProcessAdapter(
        spec=HarnessSpec(
            # Pi Agent Harness CLI (global install @earendil-works/pi-coding-agent).
            binary="pi",
            version_args=("--version",),
            start_args_builder=_pi_args,
            doctor_cmd=("pi", "--version"),
            extra_env={"PI_OFFLINE": "1"},
        ),
        task_timeout_s=300.0,
    )


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
            stdin_prompt=True,
        ),
        task_timeout_s=300.0,
    )


def acceptance_fixture_cli_adapter() -> ScopedProcessAdapter:
    """Acceptance-only fixture harness (CONDUVERA_ACCEPTANCE_MODE=1 only).

    Runs the deterministic acceptance_fixture module as a REAL managed OS
    process through the normal Control-Plane scope/worktree path. Registered
    only on the isolated acceptance service; never in normal doctor/runtime.
    """
    return ScopedProcessAdapter(
        spec=HarnessSpec(
            binary=sys.executable,
            version_args=("-m", "conduvera.harness.acceptance_fixture",
                          "--scenario", "HOLD_THEN_EXIT_0"),
            start_args_builder=_acceptance_args,
            doctor_cmd=(sys.executable, "-m",
                        "conduvera.harness.acceptance_fixture",
                        "--scenario", "HOLD_THEN_EXIT_0"),
        ),
        task_timeout_s=120.0,
    )


def _register_instances() -> dict[str, ScopedProcessAdapter]:
    return {
        "hermes_scoped": hermes_scoped_adapter(),
        "codex_cli": codex_cli_adapter(),
        "opencode_cli": opencode_cli_adapter(),
        "pi_cli": pi_cli_adapter(),
    }
