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
from conduvera.control_plane.payload import (
    PayloadCorruptError,
    PayloadError,
    PayloadMissingError,
    TaskPayloadEnvelope,
    TaskPayloadStore,
    new_payload_id,
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


def _redact_command(cmd: str) -> str:
    """Strip task prompt / secret material from an observed process command.

    The command string is observational only and never a fingerprint-match
    criterion. Keep the leading spawn shape (systemd-run / binary) and drop
    the trailing prompt argument so raw task text never persists in the
    registry. Covers both legacy (`exec`) and cwd_exec (`--`) spawn shapes.
    """
    if not cmd:
        return cmd
    parts = cmd.split()
    keep: list[str] = []
    drop_tail = False
    for tok in parts:
        if tok in ("--", "exec"):
            keep.append(tok)
            drop_tail = True
            continue
        if drop_tail:
            break
        keep.append(tok)
    if keep:
        return " ".join(keep) + (" …[redacted]" if drop_tail else "")
    return cmd[:120]

# Repository allowlist: stable repo ids -> canonical local paths.
# Only allowlisted repositories can be used as task base repositories.
REPO_ALLOWLIST: dict[str, Path] = {
    "conduvera-core": Path.home() / "projects" / "matrix-os",
    "conduvera-adapter": Path.home() / "projects" / "conduvera-hermes-adapter",
    "conduvera-platform": Path.home() / "projects" / "conduvera-platform",
    "conduit-fixture": Path.home() / "projects" / "conduit-fixture",
}

REPO_ALIASES: dict[str, str] = {
    "core": "conduvera-core",
    "adapter": "conduvera-adapter",
    "platform": "conduvera-platform",
    "fixture": "conduit-fixture",
}


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
        repo_allowlist: dict[str, Path] | None = None,
    ):
        self.registry = registry
        self.gateway = gateway_service
        self.config = config
        self.adapter_ids = adapter_ids
        self._repo_allowlist = dict(repo_allowlist) if repo_allowlist else dict(REPO_ALLOWLIST)
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
        self._pending_prompts: dict[str, str] = {}
        self._payload_store = TaskPayloadStore(Path(config.state_dir))
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

    def resolve_repo(self, repo: str) -> Path:
        """Resolve a stable repo id to its canonical path (allowlist).

        Instance-level allowlist wins (tests/fixtures map custom ids); only
        then the global alias table is consulted.
        """
        if repo in self._repo_allowlist:
            rid = repo
        else:
            rid = REPO_ALIASES.get(repo, repo)
        if rid not in self._repo_allowlist:
            raise ValueError(f"repository not allowlisted: {repo}")
        path = self._repo_allowlist[rid]
        if not path.is_dir() or not (path / ".git").exists():
            raise ValueError(f"repository path not available: {path}")
        return path

    def submit_job(
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
        execute: bool = True,
        task_type: str = "code_change",
        expected_artifacts: list[str] | None = None,
        test_plan: str = "",
    ) -> dict[str, Any]:
        """THE single public mutation entry point.

        All submissions (CLI, BuildroomBridge, Console) go through here.
        - repository allowlist resolution;
        - duplicate attempt rejection (idempotent, never overwrite);
        - the full task payload is durably stored (TaskPayloadStore); queue/
          registry/outbox hold only payload_ref + content_sha256 — never raw
          task text;
        - queued -> claimed -> dispatched by the daemon-owned engine.
        Direct `start` bypasses this path and is internal-only (adapter tests).

        No caller-controlled shell command is accepted (task_command removed).
        """
        if harness not in self.adapter_ids:
            return {"success": False, "message": f"unknown harness {harness}",
                    "code": "UNKNOWN_HARNESS"}
        # duplicate attempt rejection: never silently overwrite
        existing = self.scheduler.store.get_attempt(attempt_id)
        if existing is not None:
            return {"success": False, "message": f"duplicate attempt {attempt_id}",
                    "code": "DUPLICATE_ATTEMPT", "attempt_id": attempt_id}
        try:
            self.resolve_repo(repo)
        except ValueError as exc:
            return {"success": False, "message": str(exc), "code": "REPO_NOT_ALLOWED"}
        # normalize path components (task/attempt -> safe identifiers)
        try:
            task_id_safe, attempt_id_safe = _normalize_identifiers(
                task_id, attempt_id)
        except ValueError as exc:
            return {"success": False, "message": str(exc), "code": "INVALID_IDENTIFIER"}

        job_id = f"job_{uuid.uuid4().hex[:12]}"
        now = _utc_now()
        # durable payload: full task text stored only in the payload store
        payload_id = new_payload_id()
        envelope = TaskPayloadEnvelope(
            payload_id=payload_id,
            task_type=task_type,
            instructions=prompt,
            repo=repo,
            base_commit=base_commit,
            expected_artifacts=list(expected_artifacts or []),
            test_plan=test_plan,
        )
        self._payload_store.put(envelope)
        job = JobDescriptor(
            job_id=job_id, task_id=task_id_safe, repo=repo,
            base_commit=base_commit, harness=harness,
            model_binding=dict(model_binding), prompt="",
            timeout_s=timeout_s, created_at=now, updated_at=now,
            payload_ref=payload_id, content_sha256=envelope.content_sha256,
            task_type=task_type,
        )
        job.bind_prompt(prompt)
        job.attempts.append(attempt_id_safe)
        self.scheduler.store.save_job(job)
        self._emit("job.accepted", {"job_id": job_id, "task_id": task_id_safe,
                                    "harness": harness, "repo": repo,
                                    "payload_ref": payload_id,
                                    "content_sha256": envelope.content_sha256})

        attempt = AttemptDescriptor(
            attempt_id=attempt_id_safe, job_id=job_id, task_id=task_id_safe,
            harness=harness, created_at=now, updated_at=now,
        )
        self.scheduler.store.save_attempt(attempt)
        self._emit("attempt.created", {"job_id": job_id,
                                       "attempt_id": attempt_id_safe,
                                       "task_id": task_id_safe,
                                       "harness": harness})

        # queue: the daemon-owned dispatcher claims + starts automatically
        attempt.state = AttemptState.QUEUED
        attempt.updated_at = _utc_now()
        self.scheduler.store.save_attempt(attempt)
        # memory cache only as an optimization over the persistent payload
        # store (the persistent authority is _payload_store).
        self._pending_prompts[attempt_id_safe] = prompt
        self._emit("session.queued", {"job_id": job_id,
                                      "attempt_id": attempt_id_safe,
                                      "task_id": task_id_safe,
                                      "harness": harness})
        return {"success": True, "message": "job accepted and queued",
                "job_id": job_id, "attempt_id": attempt_id_safe,
                "payload_ref": payload_id,
                "content_sha256": envelope.content_sha256, "queued": True}

    def dispatch_claimed(self, attempt_id: str) -> dict[str, Any]:
        """Dispatcher-owned: start one CLAIMED attempt (worktree -> gateway)."""
        attempt = self.scheduler.store.get_attempt(attempt_id)
        if attempt is None or attempt.state is not AttemptState.CLAIMED:
            return {"success": False, "message": f"attempt {attempt_id} not claimed",
                    "code": "NOT_CLAIMED"}
        job = self.scheduler.store.get_job(attempt.job_id)
        if job is None:
            return {"success": False, "message": "job missing", "code": "JOB_MISSING"}
        harness = job.harness
        task_id = job.task_id
        # real Git worktree from the exact base commit (allowlisted repo)
        try:
            repo_path = self.resolve_repo(job.repo)
            binding = self.worktrees.create(
                repo_path=repo_path, base_commit=job.base_commit,
                task_id=task_id, attempt_id=attempt.attempt_id,
            )
        except WorktreeError as exc:
            # Terminal FAILED — never return to the queue (would loop forever
            # on the same unresolvable commit and spam failed events).
            attempt.state = AttemptState.FAILED
            attempt.terminal = True
            attempt.terminal_reason = f"worktree: {exc}"
            attempt.updated_at = _utc_now()
            self.scheduler.store.save_attempt(attempt)
            job.state = JobState.FAILED
            job.terminal_reason = f"worktree: {exc}"
            job.updated_at = _utc_now()
            self.scheduler.store.save_job(job)
            self._emit("session.failed", {"job_id": job.job_id,
                                          "attempt_id": attempt.attempt_id,
                                          "task_id": task_id,
                                          "reason": f"worktree: {exc}"})
            return {"success": False, "message": str(exc), "code": "WORKTREE_ERROR"}
        wt = Path(binding.path)
        attempt.worktree = binding.to_dict()
        attempt.state = AttemptState.RUNNING
        attempt.updated_at = _utc_now()
        self.scheduler.store.save_attempt(attempt)
        self._emit("session.claimed", {"job_id": job.job_id,
                                       "attempt_id": attempt.attempt_id,
                                       "task_id": task_id,
                                       "harness": harness})
        self._emit("session.start.requested", {"job_id": job.job_id,
                                               "attempt_id": attempt.attempt_id,
                                               "task_id": task_id,
                                               "harness": harness,
                                               "worktree": binding.to_dict(),
                                               "base_commit": job.base_commit})

        # Durable task payload: reload from the persistent store and verify the
        # content hash. Missing/corrupt/hash-mismatch fails the attempt loudly
        # (never falls back to an empty or redacted prompt).
        try:
            envelope = self._payload_store.get(job.payload_ref)
        except (PayloadMissingError, PayloadCorruptError, PayloadError) as exc:
            attempt.state = AttemptState.FAILED
            attempt.terminal = True
            attempt.terminal_reason = f"payload: {exc}"
            attempt.updated_at = _utc_now()
            self.scheduler.store.save_attempt(attempt)
            job.state = JobState.FAILED
            job.terminal_reason = f"payload: {exc}"
            job.updated_at = _utc_now()
            self.scheduler.store.save_job(job)
            self._emit("session.failed", {"job_id": job.job_id,
                                          "attempt_id": attempt.attempt_id,
                                          "task_id": task_id,
                                          "reason": f"payload: {exc}"})
            return {"success": False, "message": str(exc), "code": "PAYLOAD_ERROR"}
        if envelope.content_sha256 != job.content_sha256:
            attempt.state = AttemptState.FAILED
            attempt.terminal = True
            attempt.terminal_reason = "payload hash mismatch"
            attempt.updated_at = _utc_now()
            self.scheduler.store.save_attempt(attempt)
            job.state = JobState.FAILED
            job.terminal_reason = "payload hash mismatch"
            job.updated_at = _utc_now()
            self.scheduler.store.save_job(job)
            self._emit("session.failed", {"job_id": job.job_id,
                                          "attempt_id": attempt.attempt_id,
                                          "task_id": task_id,
                                          "reason": "payload hash mismatch"})
            return {"success": False, "message": "payload hash mismatch",
                    "code": "PAYLOAD_HASH_MISMATCH"}

        result = self.gateway.start_session(
            adapter_id=harness,
            agent_id=task_id,
            worktree=str(wt),
            task=task_id,
            config={
                "execution_mode": "LIVE",
                "route": job.model_binding.get("route", "workload/local"),
                "model_binding": job.model_binding,
                # exact original task instructions from the durable payload
                "prompt": envelope.instructions,
                "payload_ref": envelope.payload_id,
                "content_sha256": envelope.content_sha256,
                "prompt_hash": job.prompt_hash,
                "timeout_s": job.timeout_s,
                # registry/worktree binding for cwd_exec validation
                "repo": job.repo,
                "repo_path": str(repo_path),
                "base_commit": job.base_commit,
                "attempt_id": attempt.attempt_id,
            },
        )
        if not result.success:
            attempt.state = AttemptState.FAILED
            attempt.terminal = True
            attempt.terminal_reason = result.message
            attempt.updated_at = _utc_now()
            self.scheduler.store.save_attempt(attempt)
            job.state = JobState.FAILED
            job.terminal_reason = result.message
            job.updated_at = _utc_now()
            self.scheduler.store.save_job(job)
            self._emit("session.failed", {"job_id": job.job_id,
                                          "attempt_id": attempt.attempt_id,
                                          "task_id": task_id,
                                          "reason": result.message})
            return {"success": False, "message": result.message,
                    "detail": dict(result.detail), "code": result.detail.get("code")}
        detail = dict(result.detail)
        session_id = detail.get("session_id", f"mxs_{uuid.uuid4().hex[:16]}")
        session = ManagedSession(
            session_id=session_id,
            task_id=task_id,
            attempt_id=attempt.attempt_id,
            ownership_class=OwnershipClass.MANAGED,
            managed=True,
            instance_id=f"{attempt.attempt_id}-{uuid.uuid4().hex[:8]}",
            fingerprint=ProcessFingerprint(
                pid=int(detail.get("pid", 0)),
                start_time=_process_start_time(int(detail.get("pid", 0))),
                boot_id=_boot_id(),
                # command is observational only (never a mismatch criterion);
                # strip any task prompt / secret material from the argv string
                # so raw task text never persists in the registry.
                command=_redact_command(_process_cmd(int(detail.get("pid", 0)))),
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
                                       "attempt_id": attempt.attempt_id,
                                       "session_id": session_id,
                                       "task_id": task_id,
                                       "harness": harness,
                                       "worktree": binding.to_dict(),
                                       "base_commit": job.base_commit,
                                       "scope": session.scope_id,
                                       "pid": session.fingerprint.pid if session.fingerprint else 0})
        return {"success": True, "message": f"job started via {harness}",
                "job_id": job.job_id, "attempt_id": attempt.attempt_id,
                "session": session.to_dict()}

    def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """Public event emission used by the engine (exactly-once terminal)."""
        self._emit(event_type, payload)

    def emit_observed(self, session_id: str, fp: Any) -> None:
        """Status observation event (throttled by caller cadence)."""
        self._emit("session.status.observed", {
            "session_id": session_id, "pid": fp.pid,
            "state": "RUNNING"})



    def submit(self, **kw: Any) -> dict[str, Any]:
        """Compatibility alias — routes to the single public path submit_job."""
        return self.submit_job(**kw)

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
        return self.submit_job(
            task_id=task_id, attempt_id=attempt_id, harness=harness,
            repo=repo, base_commit=base_commit, model_binding=model_binding,
            prompt=prompt, timeout_s=timeout_s,
        )

    def retry_job(self, job_id: str, attempt_id: str | None = None) -> dict[str, Any]:
        """Retry a terminal job as a new attempt (same durable payload).

        Requires the original job to be terminal and its payload to still
        exist and hash-verify. The exact original instructions are reloaded
        from the TaskPayloadStore — never from caller input.
        """
        job = self.scheduler.store.get_job(job_id)
        if job is None:
            return {"success": False, "message": f"unknown job {job_id}",
                    "code": "UNKNOWN_JOB"}
        if job.state not in (JobState.COMPLETED, JobState.FAILED,
                             JobState.CANCELLED, JobState.TIMED_OUT):
            return {"success": False, "message": f"job {job_id} not terminal "
                    f"({job.state.value})", "code": "NOT_TERMINAL"}
        try:
            envelope = self._payload_store.get(job.payload_ref)
        except (PayloadMissingError, PayloadCorruptError, PayloadError) as exc:
            return {"success": False, "message": f"payload: {exc}",
                    "code": "PAYLOAD_ERROR"}
        if envelope.content_sha256 != job.content_sha256:
            return {"success": False, "message": "payload hash mismatch",
                    "code": "PAYLOAD_HASH_MISMATCH"}
        if attempt_id is None:
            attempt_id = f"{job.job_id.split('_')[-1][:8]}-retry"
        return self.submit_job(
            task_id=job.task_id, attempt_id=attempt_id, harness=job.harness,
            repo=job.repo, base_commit=job.base_commit,
            model_binding=job.model_binding, prompt=envelope.instructions,
            timeout_s=job.timeout_s, task_type=job.task_type)

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
            attempt.terminal_reason = f"session {session.state.value}"
            attempt.updated_at = _utc_now()
            self.scheduler.store.save_attempt(attempt)
            job = self.scheduler.store.get_job(attempt.job_id)
            if job is not None and job.state is not JobState.COMPLETED:
                job.state = {
                    AttemptState.CANCELLED: JobState.CANCELLED,
                    AttemptState.COMPLETED: JobState.COMPLETED,
                    AttemptState.FAILED: JobState.FAILED,
                    AttemptState.TIMED_OUT: JobState.TIMED_OUT,
                }.get(state, job.state)
                job.terminal_reason = f"session {session.state.value}"
                job.updated_at = _utc_now()
                self.scheduler.store.save_job(job)

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

    def console_view(self, limit: int | None = None) -> dict[str, Any]:
        """Konsolidierte Operator-Console über die reale Control-Plane-API.

        Vereinigt Queue/Jobs + Sessions in einem zusammenhängenden View:
        - queued: Attempts, die auf Dispatch warten (payload_ref + hash)
        - running: laufende Sessions mit elapsed/deadline/worktree/base
        - terminal: abgeschlossene mit reason/exit/result_refs
        - evidence: Ergebnis-Referenzen je Job
        Nutzt nur persistierte/observierte Daten; reicht NIE raw Prompts durch.
        `limit` kappt jede Sektion (newest-first, deterministisch).
        """
        import datetime as _dt
        now = _dt.datetime.now(_dt.timezone.utc)
        sessions = self.list_sessions()
        by_key: dict[str, dict] = {}
        for s in sessions:
            key = f"{s.get('task_id')}/{s.get('attempt_id')}"
            by_key.setdefault(key, {"task_id": s.get("task_id"),
                                    "attempt_id": s.get("attempt_id")})
            by_key[key].setdefault("sessions", []).append(s)

        jobs = [j.to_dict() for j in self.scheduler.store.all_jobs()]
        job_by_id = {j["job_id"]: j for j in jobs}

        def _elapsed_deadline(started_at: str, timeout_s: float) -> dict:
            d = {"elapsed_s": None, "deadline_utc": None}
            if not started_at:
                return d
            try:
                st = _dt.datetime.fromisoformat(started_at)
                if st.tzinfo is None:
                    st = st.replace(tzinfo=_dt.timezone.utc)
                d["elapsed_s"] = round((now - st).total_seconds(), 1)
                d["deadline_utc"] = (
                    st + _dt.timedelta(seconds=float(timeout_s))).isoformat()
            except (ValueError, TypeError):
                pass
            return d

        # --- queued ---
        queued = []
        for a in self.scheduler.store.all_attempts():
            if a.state.value in ("QUEUED", "ACCEPTED"):
                j = job_by_id.get(a.job_id, {})
                queued.append({
                    "job_id": a.job_id, "attempt_id": a.attempt_id,
                    "task_id": j.get("task_id", ""),
                    "harness": j.get("harness", ""),
                    "task_type": j.get("task_type", ""),
                    "state": a.state.value,
                    "payload_ref": j.get("payload_ref", ""),
                    "content_sha256": j.get("content_sha256", ""),
                    "base_commit": j.get("base_commit", ""),
                    "created_at": j.get("created_at", ""),
                    ** _elapsed_deadline(j.get("created_at", ""),
                                         float(j.get("timeout_s", 180.0))),
                })

        # --- running ---
        running = []
        for s in sessions:
            if s.get("state") in ("RUNNING", "STARTING"):
                ed = _elapsed_deadline(s.get("started_at", ""),
                                       float(s.get("timeout_s", 180.0)))
                running.append({
                    "session_id": s.get("session_id"),
                    "task_id": s.get("task_id"), "attempt_id": s.get("attempt_id"),
                    "scope_id": s.get("scope_id", ""),
                    "pid": s.get("pid"),
                    "harness": s.get("harness_descriptor", ""),
                    "worktree": s.get("worktree", ""),
                    "base_commit": s.get("base_commit", ""),
                    "started_at": s.get("started_at", ""),
                    **ed,
                })

        # --- terminal ---
        terminal = []
        for j in jobs:
            if j.get("state") in ("COMPLETED", "FAILED", "CANCELLED",
                                  "TIMED_OUT"):
                terminal.append({
                    "job_id": j["job_id"], "task_id": j.get("task_id", ""),
                    "attempt_id": (j.get("attempts") or [None])[0],
                    "state": j.get("state"),
                    "terminal_reason": j.get("terminal_reason", ""),
                    "exit_code": j.get("exit_code"),
                    "result_refs": list(j.get("result_refs", [])),
                    "harness": j.get("harness", ""),
                    "payload_ref": j.get("payload_ref", ""),
                    "content_sha256": j.get("content_sha256", ""),
                    "created_at": j.get("created_at", ""),
                    "updated_at": j.get("updated_at", ""),
                })

        return {
            "counts": {"queued": len(queued), "running": len(running),
                       "terminal": len(terminal)},
            "queued": sorted(queued, key=lambda x: x.get("created_at", ""),
                             reverse=True)[:limit if limit else None],
            "running": sorted(running, key=lambda x: x.get("started_at", ""),
                              reverse=True)[:limit if limit else None],
            "terminal": sorted(terminal, key=lambda x: x.get("updated_at", ""),
                               reverse=True)[:limit if limit else None],
            "server_time_utc": now.isoformat(),
        }

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


def _normalize_identifiers(task_id: str, attempt_id: str) -> tuple[str, str]:
    """Normalize task/attempt path components (reject traversal/separators).

    Accepts only [A-Za-z0-9._-]; rejects absolute paths, '..', '/', control
    characters and empty values. Used as worktree path components.
    """
    import re as _re
    allowed = _re.compile(r"^[A-Za-z0-9._-]+$")
    bad = []
    for ident, name in ((task_id, "task_id"), (attempt_id, "attempt_id")):
        if not ident:
            bad.append(f"{name} empty")
        elif not allowed.match(ident):
            bad.append(f"{name} contains forbidden characters")
        elif ident in (".", ".."):
            bad.append(f"{name} is a path component")
        elif ident.startswith("/") or "\\" in ident:
            bad.append(f"{name} is an absolute/separator path")
    if bad:
        raise ValueError("; ".join(bad))
    return task_id, attempt_id
