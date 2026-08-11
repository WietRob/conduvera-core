"""Conduvera Operational Harness Control Plane — persistent runtime.

MXOS-SAFETY-1 / MXOS-RUNTIME-1 / CONTROL-PLANE-V1.

Turns the proven single-session managed runtime into a persistent host
service:

- named service state under $XDG_STATE_HOME/conduvera (default
  ~/.local/state/conduvera), never /tmp;
- persistent session registry with atomic writes, mode 0600 and an explicit
  schema/version migration;
- operations: start, list, inspect/status, cancel, cleanup, reconcile;
- restart-safe reconciliation: running sessions rediscovered via full
  fingerprints; dead sessions become COMPLETED/FAILED/LOST truthfully; PID
  reuse can never control a foreign process;
- structured UNSUPPORTED for pause/steer/checkpoint (not implemented in v1).

All registry writes are atomic (tmp file + rename) and mode 0600.
"""

from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from conduvera.harness.managed_session import (
    ManagedSession,
    ManagedSessionRegistry,
    OwnershipClass,
    ProcessFingerprint,
    SessionState,
    _boot_id,
    _process_cmd,
    _process_start_time,
)
from conduvera.control_plane.scheduler import (
    AttemptDescriptor,
    AttemptState,
    JobDescriptor,
    JobState,
    Scheduler,
    SchedulerStore,
    _utc_now,
)
from conduvera.control_plane.worktree import WorktreeManager, WorktreeError

REGISTRY_SCHEMA_VERSION = 1


class Capability(str, Enum):
    """Capability-based harness selection (v1)."""

    DISCOVER = "discover"
    DOCTOR = "doctor"
    VALIDATE = "validate"
    START = "start"
    STATUS = "status"
    CANCEL = "cancel"
    COLLECT_EVIDENCE = "collect_evidence"
    CLEANUP = "cleanup"
    # capability-based (not implemented in v1 -> structured UNSUPPORTED)
    PAUSE = "pause"
    STEER = "steer"
    RESUME = "resume"
    CHECKPOINT = "checkpoint"
    ATTACH = "attach"
    STREAMING = "streaming"


@dataclass
class ControlPlaneConfig:
    """Persistent service configuration."""

    state_dir: Path
    registry_path: Path
    socket_path: Path
    worktree_base: Path
    evidence_dir: Path
    outbox_path: Path

    @classmethod
    def default(cls, state_dir: str | Path | None = None) -> "ControlPlaneConfig":
        base = Path(state_dir) if state_dir else Path(
            os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")
        ) / "conduvera"
        base = base.expanduser().resolve()
        return cls(
            state_dir=base,
            registry_path=base / "registry" / "sessions.json",
            socket_path=base / "control-plane.sock",
            worktree_base=base / "worktrees",
            evidence_dir=base / "evidence",
            outbox_path=base / "outbox" / "events.jsonl",
        )


class RegistryMigrationError(Exception):
    """Raised when the registry schema cannot be migrated safely."""


class PersistentSessionRegistry(ManagedSessionRegistry):
    """Persistent registry with schema version + migration (v1)."""

    def __init__(self, path: str | Path):
        super().__init__(path)
        self._schema_path = self.path.with_name("schema_version")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        if not self._schema_path.is_file():
            self._write_schema(REGISTRY_SCHEMA_VERSION)
            return
        try:
            current = int(self._schema_path.read_text().strip())
        except ValueError:
            raise RegistryMigrationError(
                f"registry schema file unreadable: {self._schema_path}"
            ) from None
        if current > REGISTRY_SCHEMA_VERSION:
            raise RegistryMigrationError(
                f"registry schema {current} newer than supported {REGISTRY_SCHEMA_VERSION}"
            )
        if current < REGISTRY_SCHEMA_VERSION:
            # v1 -> v1: no data migration needed yet; bump marker only.
            self._write_schema(REGISTRY_SCHEMA_VERSION)

    def _write_schema(self, version: int) -> None:
        tmp = self._schema_path.with_suffix(".tmp")
        tmp.write_text(f"{version}\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._schema_path)
        os.chmod(self._schema_path, 0o600)


def _live_fingerprint(pid: int) -> ProcessFingerprint | None:
    """Current OS fingerprint for a PID (empty when the PID is gone)."""
    if pid <= 0:
        return None
    start = _process_start_time(pid)
    if not start:
        return None
    return ProcessFingerprint(
        pid=pid,
        start_time=start,
        boot_id=_boot_id(),
        command=_process_cmd(pid),
    )


class ControlPlaneService:
    """Persistent harness control plane (in-process runtime for the daemon)."""

    PRODUCER = {"name": "conduvera-control-plane", "version": "v1",
                "adapter": "control-plane"}

    def __init__(
        self,
        *,
        registry: PersistentSessionRegistry,
        gateway_service: Any,
        config: ControlPlaneConfig,
        adapter_ids: tuple[str, ...] = ("hermes_scoped", "codex_cli",
                                        "opencode_cli", "hermes"),
        global_concurrency: int = 4,
        per_harness_limits: dict[str, int] | None = None,
        retention_s: float = 3600.0,
        repo_path: str | Path | None = None,
    ):
        self.registry = registry
        self.gateway = gateway_service
        self.config = config
        self.adapter_ids = adapter_ids
        config.state_dir.mkdir(parents=True, exist_ok=True)
        config.worktree_base.mkdir(parents=True, exist_ok=True)
        config.evidence_dir.mkdir(parents=True, exist_ok=True)
        config.outbox_path.parent.mkdir(parents=True, exist_ok=True)
        self.scheduler = Scheduler(
            store=SchedulerStore(config.state_dir / "scheduler" / "queue.json"),
            global_limit=global_concurrency,
            per_harness_limits=per_harness_limits,
            retention_s=retention_s,
        )
        self.worktrees = WorktreeManager(config.worktree_base)
        # repo_path: the Git repository MANAGED worktrees are created from.
        # Defaults to the conduvera-core checkout when running from source.
        self.repo_path = Path(repo_path).expanduser().resolve() if repo_path else (
            Path(__file__).resolve().parent.parent.parent
        )
        self._outbox = None

    def set_outbox(self, outbox: Any) -> None:
        """Attach the durable redacted event outbox (called by the daemon)."""
        self._outbox = outbox

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """Persist a lifecycle event (registry + outbox)."""
        from conduvera.evidence.contract import EventEnvelope
        envelope = EventEnvelope.create(
            event_type=event_type,
            producer={"name": "conduvera-control-plane", "version": "v1",
                      "adapter": "control-plane"},
            subject={"kind": "harness_job", "core": "conduvera-core"},
            payload=payload,
            correlation_id=str(payload.get("job_id") or payload.get("session_id") or ""),
        )
        if self._outbox is not None:
            self._outbox.append(envelope.to_dict())

    # -- reconciliation ----------------------------------------------------

    def reconcile(self) -> dict[str, Any]:
        """Restart-safe reconciliation of all registered sessions.

        For each session:
          - fingerprint matches        -> RUNNING (rediscovered, no adoption)
          - PID gone                   -> COMPLETED/FAILED (truthful terminal)
          - PID reused (fingerprint mismatch) -> LOST (never control new proc)
        External sessions are never touched.
        """
        results: dict[str, Any] = {}
        for session in self.registry.all():
            if session.ownership_class is not OwnershipClass.MANAGED:
                results[session.session_id] = {"state": session.state.value,
                                               "touched": False}
                continue
            fp = session.fingerprint
            if fp is None or fp.pid <= 0:
                results[session.session_id] = {"state": session.state.value,
                                               "touched": False}
                continue
            live = _live_fingerprint(fp.pid)
            if live is None:
                if session.state not in (SessionState.CANCELLED,
                                         SessionState.COMPLETED,
                                         SessionState.FAILED, SessionState.LOST):
                    session.state = SessionState.COMPLETED
                    session.ended_at = _utc_now()
                    self.registry.update(session)
                self._mark_attempt_terminal(session, AttemptState.COMPLETED)
                results[session.session_id] = {"state": session.state.value,
                                               "transitioned": "process_gone"}
                self._emit("session.reconciled", {"session_id": session.session_id,
                                                  "state": session.state.value,
                                                  "transitioned": "process_gone"})
            elif live.matches(fp):
                if session.state is not SessionState.RUNNING:
                    session.state = SessionState.RUNNING
                    self.registry.update(session)
                results[session.session_id] = {"state": "RUNNING",
                                               "transitioned": "rediscovered"}
                self._emit("session.reconciled", {"session_id": session.session_id,
                                                  "state": "RUNNING",
                                                  "transitioned": "rediscovered"})
            else:
                session.state = SessionState.LOST
                session.ended_at = _utc_now()
                self.registry.update(session)
                results[session.session_id] = {"state": "LOST",
                                               "transitioned": "pid_reuse"}
                self._emit("session.reconciled", {"session_id": session.session_id,
                                                  "state": "LOST",
                                                  "transitioned": "pid_reuse"})
        return results

    # -- job operations -----------------------------------------------------

    def submit(
        self,
        *,
        task_id: str,
        attempt_id: str,
        harness: str,
        repo: str,
        base_commit: str,
        model_binding: dict[str, Any],
        prompt: str,
        timeout_s: float = 120.0,
    ) -> dict[str, Any]:
        """Submit one job: accept -> create attempt -> queue/start."""
        if harness not in self.adapter_ids:
            return {"success": False, "message": f"unknown harness {harness}",
                    "code": "UNKNOWN_HARNESS"}
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        now = _utc_now()
        job = JobDescriptor(
            job_id=job_id, task_id=task_id, repo=repo, base_commit=base_commit,
            harness=harness, model_binding=dict(model_binding), prompt=prompt,
            timeout_s=timeout_s, created_at=now, updated_at=now,
        )
        job.attempts.append(attempt_id)
        self.scheduler.store.save_job(job)
        self._emit("job.accepted", {"job_id": job_id, "task_id": task_id,
                                    "harness": harness})

        attempt = AttemptDescriptor(
            attempt_id=attempt_id, job_id=job_id, task_id=task_id,
            harness=harness, created_at=now, updated_at=now,
        )
        self.scheduler.store.save_attempt(attempt)
        self._emit("attempt.created", {"job_id": job_id, "attempt_id": attempt_id,
                                       "task_id": task_id, "harness": harness})

        can_start, reason = self.scheduler.can_start(harness)
        if can_start:
            return self._start_attempt(job, attempt)
        # Queue the attempt (bounded concurrency) — deterministic.
        attempt.state = AttemptState.QUEUED
        attempt.updated_at = _utc_now()
        self.scheduler.store.save_attempt(attempt)
        self._emit("session.queued", {"job_id": job_id, "attempt_id": attempt_id,
                                      "task_id": task_id, "harness": harness,
                                      "reason": reason})
        return {"success": True, "message": f"job queued ({reason})",
                "job_id": job_id, "attempt_id": attempt_id, "queued": True}

    def start(
        self,
        *,
        task_id: str,
        attempt_id: str,
        harness: str,
        repo: str,
        base_commit: str,
        model_binding: dict[str, Any],
        prompt: str,
        timeout_s: float = 120.0,
        worktree: str | None = None,
        execution_mode: str = "LIVE",
    ) -> dict[str, Any]:
        """Start one job (compat path: submit with immediate start)."""
        return self.submit(
            task_id=task_id, attempt_id=attempt_id, harness=harness,
            repo=repo, base_commit=base_commit, model_binding=model_binding,
            prompt=prompt, timeout_s=timeout_s,
        )

    def _start_attempt(
        self,
        job: JobDescriptor,
        attempt: AttemptDescriptor,
    ) -> dict[str, Any]:
        """Start one queued/accepted attempt: real worktree -> gateway -> session."""
        harness = job.harness
        task_id = job.task_id
        attempt_id = attempt.attempt_id
        # 1) Real Git worktree from the exact base commit (proven via Git).
        try:
            binding = self.worktrees.create(
                repo_path=self.repo_path, base_commit=job.base_commit,
                task_id=task_id, attempt_id=attempt_id,
            )
        except WorktreeError as exc:
            attempt.state = AttemptState.FAILED
            attempt.updated_at = _utc_now()
            self.scheduler.store.save_attempt(attempt)
            self._emit("session.failed", {"job_id": job.job_id,
                                          "attempt_id": attempt_id,
                                          "task_id": task_id,
                                          "reason": f"worktree: {exc}"})
            return {"success": False, "message": str(exc),
                    "code": "WORKTREE_ERROR"}
        wt = Path(binding.path)
        attempt.worktree = binding.to_dict()
        attempt.state = AttemptState.RUNNING
        attempt.updated_at = _utc_now()
        self.scheduler.store.save_attempt(attempt)
        self._emit("session.start.requested", {"job_id": job.job_id,
                                               "attempt_id": attempt_id,
                                               "task_id": task_id,
                                               "harness": harness,
                                               "worktree": binding.to_dict(),
                                               "base_commit": job.base_commit})

        result = self.gateway.start_session(
            adapter_id=harness,
            agent_id=task_id,
            worktree=str(wt),
            task=task_id,
            config={
                "execution_mode": "LIVE",
                "route": job.model_binding.get("route", "workload/local"),
                "model_binding": job.model_binding,
                "prompt": job.prompt,
                "timeout_s": job.timeout_s,
            },
        )
        if not result.success:
            attempt.state = AttemptState.FAILED
            attempt.updated_at = _utc_now()
            self.scheduler.store.save_attempt(attempt)
            self._emit("session.failed", {"job_id": job.job_id,
                                          "attempt_id": attempt_id,
                                          "task_id": task_id,
                                          "reason": result.message})
            return {"success": False, "message": result.message,
                    "detail": dict(result.detail), "code": result.detail.get("code")}
        detail = dict(result.detail)
        session_id = detail.get("session_id", f"mxs_{uuid.uuid4().hex[:16]}")
        session = ManagedSession(
            session_id=session_id,
            task_id=task_id,
            attempt_id=attempt_id,
            ownership_class=OwnershipClass.MANAGED,
            managed=True,
            instance_id=f"{attempt_id}-{uuid.uuid4().hex[:8]}",
            fingerprint=ProcessFingerprint(
                pid=int(detail.get("pid", 0)),
                start_time=_process_start_time(int(detail.get("pid", 0))),
                boot_id=_boot_id(),
                command=_process_cmd(int(detail.get("pid", 0))),
            ),
            scope_id=str(detail.get("pgid", "") or detail.get("scope", "")),
            state=SessionState.RUNNING,
            created_at=_utc_now(),
            started_at=_utc_now(),
            worktree=str(wt),
            base_commit=job.base_commit,
            adapter_session_id=str(detail.get("session_id", "")),
            harness_descriptor=harness,
            model_binding=dict(job.model_binding),
            timeout_s=job.timeout_s,
        )
        self.registry.register(session)
        attempt.session_id = session_id
        attempt.scope_id = session.scope_id
        attempt.updated_at = _utc_now()
        self.scheduler.store.save_attempt(attempt)
        job.state = JobState.RUNNING
        job.updated_at = _utc_now()
        self.scheduler.store.save_job(job)
        self._emit("session.started", {"job_id": job.job_id,
                                       "attempt_id": attempt_id,
                                       "session_id": session_id,
                                       "task_id": task_id,
                                       "harness": harness,
                                       "worktree": binding.to_dict(),
                                       "base_commit": job.base_commit,
                                       "scope": session.scope_id,
                                       "pid": session.fingerprint.pid if session.fingerprint else 0})
        return {"success": True, "message": f"job started via {harness}",
                "job_id": job.job_id, "attempt_id": attempt_id,
                "session": session.to_dict()}

    def status(self, session_id: str) -> dict[str, Any]:
        session = self.registry.get(session_id)
        if session is None:
            return {"success": False, "message": "unknown session",
                    "code": "UNKNOWN_SESSION"}
        if session.ownership_class is not OwnershipClass.MANAGED:
            return {"success": False, "message": "not a managed session",
                    "code": "NOT_MANAGED",
                    "ownership_class": session.ownership_class.value}
        fp = session.fingerprint
        if fp is None or fp.pid <= 0:
            return {"success": True, "state": session.state.value,
                    "session_id": session_id}
        live = _live_fingerprint(fp.pid)
        if live is None:
            if session.state not in (SessionState.CANCELLED, SessionState.COMPLETED,
                                     SessionState.FAILED, SessionState.LOST):
                session.state = SessionState.COMPLETED
                session.ended_at = _utc_now()
                self.registry.update(session)
            return {"success": True, "state": session.state.value,
                    "session_id": session_id}
        if not live.matches(fp):
            session.state = SessionState.LOST
            session.ended_at = _utc_now()
            self.registry.update(session)
            return {"success": True, "state": "LOST", "session_id": session_id}
        return {"success": True, "state": "RUNNING", "session_id": session_id,
                "pid": fp.pid, "scope_id": session.scope_id}

    def cancel(self, session_id: str) -> dict[str, Any]:
        session = self.registry.get(session_id)
        if session is None:
            return {"success": False, "message": "unknown session",
                    "code": "UNKNOWN_SESSION"}
        if session.ownership_class is not OwnershipClass.MANAGED:
            return {"success": False, "message":
                    "cancel rejected: session is not MANAGED (control_rights=none)",
                    "code": "EXTERNAL_SESSION_NOT_CONTROLLABLE",
                    "ownership_class": session.ownership_class.value}
        result = self.gateway.cancel_session(
            adapter_id=session.harness_descriptor or "hermes",
            session_id=session.adapter_session_id or session_id,
        )
        if result.success:
            session.state = SessionState.CANCELLED
            session.ended_at = _utc_now()
            self.registry.update(session)
            self._mark_attempt_terminal(session, AttemptState.CANCELLED)
            self._emit("session.cancelled", {"session_id": session_id,
                                             "task_id": session.task_id,
                                             "attempt_id": session.attempt_id})
            return {"success": True, "state": "CANCELLED", "session_id": session_id}
        # Fallback after service restart: the adapter in-memory session map is
        # gone, but the scope/cgroup still owns the process. Terminate the
        # owned systemd scope directly (fingerprint-verified) — never a
        # foreign process.
        if session.scope_id and session.scope_id.endswith(".scope"):
            fp = session.fingerprint
            if fp is not None and fp.pid > 0:
                import subprocess as _sp
                r = _sp.run(["systemctl", "--user", "kill", session.scope_id, "-s", "SIGKILL"],
                            capture_output=True, text=True, timeout=15)
                if r.returncode == 0:
                    session.state = SessionState.CANCELLED
                    session.ended_at = _utc_now()
                    self.registry.update(session)
                    self._mark_attempt_terminal(session, AttemptState.CANCELLED)
                    self._emit("session.cancelled", {"session_id": session_id,
                                                     "task_id": session.task_id,
                                                     "attempt_id": session.attempt_id})
                    return {"success": True, "state": "CANCELLED",
                            "session_id": session_id,
                            "message": f"cancelled via scope {session.scope_id}"}
        return {"success": False, "message": result.message, "detail": dict(result.detail)}

    def _mark_attempt_terminal(
        self, session: ManagedSession, state: AttemptState
    ) -> None:
        """Mark the scheduler attempt terminal (synchronized with session state)."""
        attempt = self.scheduler.store.get_attempt(session.attempt_id)
        if attempt is not None and not attempt.terminal:
            attempt.state = state
            attempt.terminal = True
            attempt.updated_at = _utc_now()
            self.scheduler.store.save_attempt(attempt)

    def cleanup(self, session_id: str) -> dict[str, Any]:
        """Remove only session-owned temporary resources (worktree + evidence)."""
        session = self.registry.get(session_id)
        if session is None:
            return {"success": False, "message": "unknown session",
                    "code": "UNKNOWN_SESSION"}
        if session.ownership_class is not OwnershipClass.MANAGED:
            return {"success": False, "message": "external session not cleanup-able",
                    "code": "NOT_MANAGED"}
        wt = Path(session.worktree) if session.worktree else None
        removed = []
        if wt is not None and wt.exists() and wt.is_relative_to(self.config.worktree_base):
            shutil.rmtree(wt)
            removed.append(str(wt))
        return {"success": True, "message": "cleanup completed",
                "removed": removed, "session_id": session_id}

    def list_sessions(self) -> list[dict[str, Any]]:
        out = []
        for s in sorted(self.registry.all(), key=lambda x: x.created_at):
            d = s.to_dict()
            d.pop("model_binding", None)  # redacted in listings
            out.append(d)
        return out

    def list_jobs(self) -> list[dict[str, Any]]:
        jobs: dict[str, dict[str, Any]] = {}
        for s in self.registry.all():
            if s.ownership_class is not OwnershipClass.MANAGED:
                continue
            key = f"{s.task_id}/{s.attempt_id}"
            jobs.setdefault(key, {
                "task_id": s.task_id, "attempt_id": s.attempt_id,
                "harness": s.harness_descriptor, "sessions": [],
                "latest_state": "",
            })
            jobs[key]["sessions"].append(s.session_id)
            jobs[key]["latest_state"] = s.state.value
        return list(jobs.values())

    # -- capability declarations -------------------------------------------

    def capabilities(self, harness: str) -> dict[str, str]:
        supported = {c.value: "supported" for c in (
            Capability.DISCOVER, Capability.DOCTOR, Capability.VALIDATE,
            Capability.START, Capability.STATUS, Capability.CANCEL,
            Capability.COLLECT_EVIDENCE, Capability.CLEANUP)}
        unsupported = {c.value: "UNSUPPORTED" for c in (
            Capability.PAUSE, Capability.STEER, Capability.RESUME,
            Capability.CHECKPOINT, Capability.ATTACH, Capability.STREAMING)}
        return {**supported, **unsupported}

    def doctor(self) -> dict[str, Any]:
        report = {"ok": True, "state_dir": str(self.config.state_dir),
                  "registry_schema": REGISTRY_SCHEMA_VERSION,
                  "harnesses": {}}
        for hid in self.adapter_ids:
            try:
                hc = self.gateway._load_adapter(hid).health_check()
                report["harnesses"][hid] = {
                    "ok": bool(hc.success), "message": hc.message,
                    "enabled": True}
                if not hc.success:
                    report["ok"] = False
            except Exception as exc:  # noqa: BLE001 - structured doctor
                report["harnesses"][hid] = {
                    "ok": False, "message": f"unavailable: {exc}", "enabled": False}
        report["registry_permissions_ok"] = self.registry.permission_ok()
        if not report["registry_permissions_ok"]:
            report["ok"] = False
        return report
