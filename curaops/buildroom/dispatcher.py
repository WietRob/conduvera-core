"""Buildroom execution dispatcher — single selection authority.

Strangler dispatcher connecting the proven ManagedBuildroomCaller with the
actual Buildroom entry point. The legacy path stays the DEFAULT; an
explicitly approved canary task may run on the managed path.

Conduvera Core
  -> BuildroomExecutionDispatcher
       |-- legacy        -> existing Buildroom orchestrator
       `-- managed_canary -> ManagedBuildroomCaller -> TaskBinding ->
            Backend-Policy -> HarnessGatewayService -> Hermes -> LiteLLM
            -> ODS/ai-stack text mode -> MXOS-EVIDENCE ->
            No-Progress-Reconciliation

AUTHORITY BOUNDARIES (this module owns ONLY the path selection):
- No second task/policy/state/evidence authority.
- Conduvera Core stays task/attempt/policy/evidence authority.
- HarnessGatewayService stays the harness-lifecycle boundary.
- LiteLLM stays the model gateway; ODS/ai-stack stays the runtime/GPU/
  service authority; BWS stays the secrets authority.
- `ai-stack model use` remains exclusively the operator/AI-stack interface.

MODES:
- legacy: default; exact existing behaviour; ManagedBuildroomCaller is
  never called.
- managed_canary: ONLY explicitly approved canary task IDs run via
  ManagedBuildroomCaller; anything else fails closed. No dual-run, no
  shadow spawn with duplicated side effects.

CONFIG: single authority — contracts/buildroom-execution-dispatcher.yaml
(`buildroom.execution_path` + `buildroom.canary_tasks`), aufgelöst über
expliziter Pfad -> CONDUVERA_BUILDROOM_DISPATCHER -> Paketressource.
Fixtures unter fixtures/buildroom/ sind ausschliesslich Testdaten.
Missing -> legacy (konservativ). Invalid mode/task id -> CONFIG_INVALID.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from curaops.buildroom.managed_execution import (
    ManagedBuildroomCaller,
    ManagedExecutionResult,
)

MODE_LEGACY = "legacy"
MODE_MANAGED_CANARY = "managed_canary"
VALID_MODES = (MODE_LEGACY, MODE_MANAGED_CANARY)

# Canonical runtime config layer (mirrors harness-registry resolution):
# explicit path -> CONDUVERA_BUILDROOM_DISPATCHER env -> package resource.
_DISPATCHER_ENV_VAR = "CONDUVERA_BUILDROOM_DISPATCHER"
_PACKAGE_DISPATCHER = "contracts/buildroom-execution-dispatcher.yaml"
# Task-ID-Schema der TaskBinding-Validierung (keine zweite Authority — gleiche
# Regex wie curaops.buildroom.task_binding, geprüft beim Config-Laden).
_CANARY_ID_RE = None  # lazy import


def _task_id_re():
    global _CANARY_ID_RE
    if _CANARY_ID_RE is None:
        from curaops.buildroom.task_binding import _TASK_ID_RE

        _CANARY_ID_RE = _TASK_ID_RE
    return _CANARY_ID_RE


def _pid_alive(pid: int) -> bool:
    """True wenn der Prozess lebt (Liveness-Prüfung für stale Leases)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # existiert, aber fremd
    return True


def _process_fingerprint() -> dict:
    """Fingerprint des aktuellen Prozesses: PID + Create-Time + Boot-ID.

    PID allein ist gegen PID-Reuse nicht abgesichert (ein neuer Prozess
    kann dieselbe PID erben). Boot-ID identifiziert den System-Boot
    eindeutig; die Prozess-Create-Time stammt aus /proc/<pid>/stat
    (field 22, Startzeit in Clockticks seit Boot).
    """
    pid = os.getpid()
    boot_id = ""
    try:
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(
            encoding="utf-8").strip()
    except OSError:
        pass
    create_time_ticks = ""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        # Feld 22 (Startzeit) nach der schließenden Klammer des comm-Feldes.
        after = stat.rsplit(")", 1)[1].split()
        if len(after) >= 20:
            create_time_ticks = after[19]
    except (OSError, IndexError, ValueError):
        pass
    return {"pid": pid, "boot_id": boot_id, "create_time_ticks": create_time_ticks}


class DispatcherConfigError(ValueError):
    """Raised when the dispatcher config is structurally invalid."""


@dataclass(frozen=True)
class DispatcherConfig:
    execution_path: str = MODE_LEGACY
    canary_tasks: tuple[str, ...] = ()

    @classmethod
    def load(cls, path: str | Path | None = None) -> "DispatcherConfig":
        """Load from the canonical config layer (never fixtures by default).

        Priority: explicit path -> CONDUVERA_BUILDROOM_DISPATCHER env ->
        package resource contracts/buildroom-execution-dispatcher.yaml.
        Missing -> legacy (conservative, backward compatible).
        Invalid YAML/mode/task id -> DispatcherConfigError (CONFIG_INVALID).
        """
        import os

        candidates: list[Path] = []
        if path is not None:
            candidates.append(Path(path).expanduser())
        env_val = os.environ.get(_DISPATCHER_ENV_VAR, "").strip()
        if env_val:
            candidates.append(Path(env_val).expanduser())
        cfg_path: Path | None = None
        for cand in candidates:
            if cand.is_file():
                cfg_path = cand.resolve()
                break
        if cfg_path is None:
            # Package resource (installed) / repo-relative contracts/.
            try:
                from importlib import resources

                pkg_res = resources.files("curaops") / _PACKAGE_DISPATCHER
                if pkg_res.is_file():
                    cfg_path = Path(str(pkg_res))
            except Exception:
                pass
        if cfg_path is None:
            repo_rel = Path(__file__).resolve().parents[2] / _PACKAGE_DISPATCHER
            if repo_rel.is_file():
                cfg_path = repo_rel.resolve()
        if cfg_path is None or not cfg_path.is_file():
            # Fehlende Konfiguration -> legacy (Vertrag: fehlend = legacy).
            return cls()
        try:
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise DispatcherConfigError("CONFIG_INVALID") from exc
        br = data.get("buildroom", {})
        if not isinstance(br, dict):
            raise DispatcherConfigError("CONFIG_INVALID")
        mode = br.get("execution_path", MODE_LEGACY)
        if mode not in VALID_MODES:
            raise DispatcherConfigError(f"CONFIG_INVALID: execution_path={mode!r}")
        canary = br.get("canary_tasks", [])
        if not isinstance(canary, list):
            raise DispatcherConfigError("CONFIG_INVALID: canary_tasks kein list")
        id_re = _task_id_re()
        for t in canary:
            if not id_re.fullmatch(str(t)):
                raise DispatcherConfigError(f"CONFIG_INVALID: canary task id {t!r} entspricht nicht ^t_[a-f0-9]+$")
        return cls(execution_path=mode, canary_tasks=tuple(str(t) for t in canary))


@dataclass
class DispatchResult:
    """Result of one dispatcher invocation (path selection + execution)."""

    task_id: str
    execution_path: str
    attempt_id: str
    status: str  # completed | legacy_delegated | canary_blocked | policy_blocked | hold | failed | duplicate_attempt
    detail: dict[str, Any] = field(default_factory=dict)
    managed_result: ManagedExecutionResult | None = None
    final_status_readable: str = ""


class BuildroomExecutionDispatcher:
    """Selects the execution path; owns NO second authority.

    - `resolve_path(task_id)` is the pure selection function.
    - `dispatch(...)` runs the selected path with single-writer per attempt
      (one lease file per attempt_id; a second dispatch for the same attempt
      fails closed as DUPLICATE_ATTEMPT).
    """

    def __init__(
        self,
        *,
        config_path: str | Path | None = None,
        leases_dir: str | Path,
        managed_caller: ManagedBuildroomCaller | None = None,
        legacy_runner: Any = None,
    ):
        self._config = DispatcherConfig.load(config_path)
        self._leases_dir = Path(leases_dir).expanduser().resolve()
        self._leases_dir.mkdir(parents=True, exist_ok=True)
        # managed_caller injected for tests; productive path constructs it
        # with explicit execution_mode (never defaulted).
        self._managed_caller = managed_caller
        # legacy_runner: callable delegating to the existing orchestrator.
        # Default None -> a subprocess invocation of the legacy CLI entry.
        self._legacy_runner = legacy_runner

    # -- public selection --------------------------------------------------

    def resolve_path(self, task_id: str) -> str:
        """Pure path selection for a task ID.

        legacy (default) unless the config explicitly selects
        managed_canary AND the task ID is on the canary allowlist.
        """
        if self._config.execution_path == MODE_MANAGED_CANARY:
            if task_id in self._config.canary_tasks:
                return MODE_MANAGED_CANARY
            return MODE_LEGACY  # non-canary -> legacy, not a managed spawn
        return MODE_LEGACY

    # -- public execution --------------------------------------------------

    def dispatch(
        self,
        *,
        task_id: str,
        task_description: str,
        phase: str = "BUILDER",
        board: str = "conduvera",
        cycle: int | None = None,
        backend: str = "native",
        evidence_fingerprint: str = "",
        log_fingerprint: str = "",
        worktree_root: str | Path | None = None,
        caller_args: dict[str, Any] | None = None,
        live: bool = False,
    ) -> DispatchResult:
        """Run one task through the selected path (single-writer per attempt)."""
        path = self.resolve_path(task_id)

        if path == MODE_MANAGED_CANARY:
            return self._dispatch_managed(
                task_id=task_id, task_description=task_description, phase=phase,
                board=board, cycle=cycle, backend=backend,
                evidence_fingerprint=evidence_fingerprint,
                log_fingerprint=log_fingerprint, worktree_root=worktree_root,
                caller_args=caller_args or {},
            )

        # legacy: exact existing behaviour; never touches ManagedBuildroomCaller.
        return self._dispatch_legacy(task_id=task_id, task_description=task_description,
                                     live=live)

    # -- internals ---------------------------------------------------------

    def _attempt_lease(self, attempt_id: str) -> Path:
        return self._leases_dir / f"{attempt_id}.lease.json"

    def _acquire_attempt_lease(self, task_id: str, attempt_id: str) -> bool:
        """ATOMIC single-writer lease (multiprocess-safe, ARBEIT 5).

        Uses O_CREAT|O_EXCL so exactly ONE competing process wins for the
        same attempt id; the others get False (DUPLICATE_ATTEMPT). A stale
        lease from a crashed process is detected via owner pid liveness and
        can be reclaimed only by the same owner task (never a foreign one).
        """
        lease = self._attempt_lease(attempt_id)
        # Stale-Reclaim atomar machen: Zwei Prozesse dürfen nicht beide die
        # verwaiste Lease löschen und dann beide O_EXCL gewinnen. Eine
        # Reclaim-Lock-Datei (flock) serialisiert den unlink+create-Schritt.
        reclaim_lock = self._leases_dir / f".{attempt_id}.reclaim"
        try:
            rl_fd = os.open(str(reclaim_lock), os.O_CREAT | os.O_RDWR, 0o600)
        except OSError:
            rl_fd = -1
        try:
            if rl_fd >= 0:
                import fcntl

                fcntl.flock(rl_fd, fcntl.LOCK_EX)
            if lease.exists():
                try:
                    owner = json.loads(lease.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    owner = {}
                owner_pid = int(owner.get("pid", 0) or 0)
                # PID-Reuse-Schutz: gleiche PID allein reicht nicht. Die
                # Lease gilt nur als live, wenn Boot-ID UND Create-Time
                # (falls in der Lease vorhanden) mit dem aktuellen
                # Fingerprint dieses PIDs übereinstimmen. Weicht die
                # Create-Time ab, ist die PID einem neuen Prozess
                # zugefallen -> Lease ist stale.
                stale = False
                if not owner_pid:
                    stale = True
                elif not _pid_alive(owner_pid):
                    stale = True
                else:
                    boot_id = owner.get("boot_id", "") or ""
                    ctime = owner.get("create_time_ticks", "") or ""
                    if boot_id:
                        cur_boot = ""
                        try:
                            cur_boot = Path("/proc/sys/kernel/random/boot_id").read_text(
                                encoding="utf-8").strip()
                        except OSError:
                            pass
                        if cur_boot and boot_id != cur_boot:
                            stale = True  # System neu gebootet
                    if ctime and not stale:
                        try:
                            cur_ctime = ""
                            stat = Path(f"/proc/{owner_pid}/stat").read_text(encoding="utf-8")
                            after = stat.rsplit(")", 1)[1].split()
                            if len(after) >= 20:
                                cur_ctime = after[19]
                            if cur_ctime and cur_ctime != ctime:
                                stale = True  # PID-Reuse: andere Create-Time
                        except OSError:
                            stale = True
                if stale and owner.get("task_id") == task_id:
                    lease.unlink()  # verwaiste Lease desselben Tasks reklamieren
                else:
                    return False
            try:
                fd = os.open(str(lease), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                return False
            except OSError:
                return False
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                fp = _process_fingerprint()
                json.dump({
                    "schema": "buildroom.dispatcher.lease.v1",
                    "task_id": task_id,
                    "attempt_id": attempt_id,
                    "execution_path": self.resolve_path(task_id),
                    "pid": os.getpid(),
                    "boot_id": fp["boot_id"],
                    "create_time_ticks": fp["create_time_ticks"],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }, f, indent=2, ensure_ascii=False)
            return True
        finally:
            if rl_fd >= 0:
                import fcntl

                try:
                    fcntl.flock(rl_fd, fcntl.LOCK_UN)
                except OSError:
                    pass
                os.close(rl_fd)
                # Reclaim-Lock-Datei NICHT löschen: unlink während andere
                # Prozesse den flock halten, erzeugt einen neuen Inode —
                # dann serialisieren zwei verschiedene Datei-Locks nicht
                # mehr gegeneinander (Multiprocess-Race). Die Lock-Datei
                # bleibt als dauerhafter Serialisierer liegen (0 Bytes).

    def _release_attempt_lease(self, attempt_id: str) -> None:
        """Release ONLY the lease owned by this process (no foreign release)."""
        lease = self._attempt_lease(attempt_id)
        try:
            owner = json.loads(lease.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            owner = {}
        if int(owner.get("pid", 0) or 0) == os.getpid():
            lease.unlink()

    def _dispatch_managed(self, *, task_id: str, task_description: str, phase: str,
                          board: str, cycle: int | None, backend: str,
                          evidence_fingerprint: str, log_fingerprint: str,
                          worktree_root: str | Path | None,
                          caller_args: dict[str, Any]) -> DispatchResult:
        attempt_id = f"ATT-{uuid.uuid4().hex[:8].upper()}"
        if not self._acquire_attempt_lease(task_id, attempt_id):
            return DispatchResult(
                task_id=task_id, execution_path=MODE_MANAGED_CANARY,
                attempt_id=attempt_id, status="duplicate_attempt",
                final_status_readable="DUPLICATE_ATTEMPT: gleiche Attempt-ID bereits gestartet",
            )
        try:
            if self._managed_caller is None:
                # Productive construction: explicit execution_mode required.
                self._managed_caller = ManagedBuildroomCaller(
                    state_path=Path(caller_args.pop("state_path", ".")),
                    route_manifest=caller_args.pop("route_manifest", "."),
                    producer=caller_args.pop("producer", {"name": "conduvera-core", "version": "0.1.0"}),
                    execution_mode=caller_args.pop("execution_mode", None),
                    **caller_args,
                )
            result = self._managed_caller.execute(
                task_description=task_description, phase=phase, board=board,
                cycle=cycle, task_id=task_id, backend=backend,
                evidence_fingerprint=evidence_fingerprint,
                log_fingerprint=log_fingerprint, worktree_root=worktree_root,
            )
            status = result.status
            if status == "policy_blocked":
                status = "policy_blocked"
            elif status == "hold":
                status = "hold"
            elif status == "completed":
                status = "completed"
            return DispatchResult(
                task_id=task_id, execution_path=MODE_MANAGED_CANARY,
                attempt_id=attempt_id, status=status,
                detail={"policy_decision": result.policy_decision,
                        "reconciliation": result.reconciliation},
                managed_result=result,
                final_status_readable=result.final_status_readable,
            )
        finally:
            self._release_attempt_lease(attempt_id)

    def _dispatch_legacy(self, *, task_id: str, task_description: str,
                         live: bool = False) -> DispatchResult:
        """legacy: execute the REAL legacy entrypoint as an isolated subprocess.

        The actual buildroom_loop.py CLI (productive installation
        ~/.hermes/scripts/buildroom_loop.py, or the frozen repo copy) is
        invoked as the existing entry point — ManagedBuildroomCaller is
        never called.

        live=False (Default): isolated proof run (separate HOME/HERMES_HOME,
        own state path, no live-state drift, bounded timeout).
        live=True: productive tick against the real ~/.hermes state (used
        by the installed autopilot wrapper).
        """
        if self._legacy_runner is not None:
            result = self._legacy_runner(task_id=task_id, task_description=task_description)
            return DispatchResult(
                task_id=task_id, execution_path=MODE_LEGACY,
                attempt_id="", status="legacy_delegated",
                detail={"legacy_result": str(result)},
                final_status_readable="LEGACY: an bestehenden Orchestrator delegiert",
            )
        # Productive default: run the real entrypoint (isolated or live).
        return _run_legacy_entrypoint(task_id=task_id, task_description=task_description,
                                      live=live)


def _find_legacy_entrypoint() -> Path | None:
    """Resolve the actual buildroom_loop.py (productive install first)."""
    candidates = [
        Path.home() / ".hermes/scripts/buildroom_loop.py",
        Path(__file__).resolve().parents[2] / "legacy/buildroom/source/buildroom_loop.py",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _run_legacy_entrypoint(*, task_id: str, task_description: str,
                           timeout_s: int = 120,
                           isolated_home: Path | None = None,
                           live: bool = False) -> DispatchResult:
    """Run buildroom_loop.py --legacy-peekxd (or generic --project) as a
    subprocess.

    isolate=True (Default): separates HOME/HERMES_HOME, own state path —
    the PROOF mode (EVIDENZ C: no live-state drift). The caller may prep a
    terminal phase in the isolated state so the orchestrator ends cleanly.

    isolate=False (live=True): the PRODUCTIVE tick mode used by the
    installed autopilot wrapper — buildroom_loop.py runs against the real
    ~/.hermes state exactly like today, so the orchestrator actually
    advances the live state. ManagedBuildroomCaller is never called.

    Returns a DispatchResult with status legacy_completed (exit 0) or
    legacy_failed (non-zero exit/timeout), plus the state/evidence report.
    """
    import os
    import subprocess
    import tempfile

    entry = _find_legacy_entrypoint()
    if entry is None:
        return DispatchResult(
            task_id=task_id, execution_path=MODE_LEGACY, attempt_id="",
            status="legacy_failed",
            detail={"error": "LEGACY_ENTRYPOINT_NOT_FOUND"},
            final_status_readable="LEGACY: buildroom_loop.py nicht gefunden",
        )

    if live:
        # Produktiver Tick: echte Umgebung, echter State (kein isoliertes
        # HOME) — der Autopilot liest danach den LIVE-State.
        try:
            proc = subprocess.run(
                [sys.executable, str(entry), "--project", "peekxd"],
                capture_output=True, text=True, timeout=timeout_s,
            )
            report = {
                "entrypoint": str(entry),
                "live": True,
                "exit_code": proc.returncode,
                "process_exited": True,
                "stdout_tail": proc.stdout[-2000:],
                "stderr_tail": proc.stderr[-2000:],
            }
            status = "legacy_completed" if proc.returncode == 0 else "legacy_failed"
            return DispatchResult(
                task_id=task_id, execution_path=MODE_LEGACY, attempt_id="",
                status=status, detail=report,
                final_status_readable=(
                    f"LEGACY: {entry.name} exit={proc.returncode} "
                    f"(produktiver Tick, echter State)"
                ),
            )
        except subprocess.TimeoutExpired:
            return DispatchResult(
                task_id=task_id, execution_path=MODE_LEGACY, attempt_id="",
                status="legacy_failed",
                detail={"error": "LEGACY_TIMEOUT", "timeout_s": timeout_s},
                final_status_readable=f"LEGACY: Timeout nach {timeout_s}s (live)",
            )

    own_home = Path(isolated_home) if isolated_home else Path(tempfile.mkdtemp(prefix="buildroom-legacy-iso-"))
    own_home.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["HOME"] = str(own_home)
    env["HERMES_HOME"] = str(own_home / ".hermes")
    (own_home / ".hermes").mkdir(parents=True, exist_ok=True)

    # Isolierter State: terminale Phase -> Orchestrator endet sauber mit
    # PHASE_ALREADY_TERMINAL (exit 0), ohne echte Research-/Hermes-Spawns.
    evidence_dir = own_home / ".hermes/research-vault/ops/peekxd-buildroom-v09"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "orchestrator-state.json").write_text(json.dumps({
        "cycle": 1, "phase": "STOPPED_AFTER_CANARY_CHECK", "status": "DONE",
        "pr_open": None, "current_candidate": None, "last_run": None,
        "task_bindings": {}, "attempts": {},
    }, indent=2), encoding="utf-8")

    try:
        proc = subprocess.run(
            [sys.executable, str(entry), "--legacy-peekxd"],
            capture_output=True, text=True, timeout=timeout_s,
            env=env, cwd=str(own_home),
        )
        exit_code = proc.returncode
        stdout = proc.stdout[-2000:]
        stderr = proc.stderr[-2000:]
        lock_file = evidence_dir / ".orchestrator-lock"
        state_file = evidence_dir / "orchestrator-state.json"
        report = {
            "entrypoint": str(entry),
            "isolated_home": str(own_home),
            "exit_code": exit_code,
            # Die Lock-Datei kann nach Prozessende existieren (Artefakt);
            # der flock selbst ist mit dem Prozess-Exit automatisch frei.
            "lock_file_present": lock_file.exists(),
            "process_exited": True,
            "state_after": json.loads(state_file.read_text(encoding="utf-8"))
            if state_file.is_file() else None,
            "stdout_tail": stdout,
            "stderr_tail": stderr,
        }
        status = "legacy_completed" if exit_code == 0 else "legacy_failed"
        return DispatchResult(
            task_id=task_id, execution_path=MODE_LEGACY, attempt_id="",
            status=status, detail=report,
            final_status_readable=(
                f"LEGACY: {entry.name} exit={exit_code} (isolierte Umgebung, "
                f"kein Managed-Spawn, Live-State unberührt)"
            ),
        )
    except subprocess.TimeoutExpired:
        return DispatchResult(
            task_id=task_id, execution_path=MODE_LEGACY, attempt_id="",
            status="legacy_failed",
            detail={"error": "LEGACY_TIMEOUT", "timeout_s": timeout_s},
            final_status_readable=f"LEGACY: Timeout nach {timeout_s}s (isoliert)",
        )
