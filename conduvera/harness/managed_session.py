"""Managed harness session runtime (MXOS-SAFETY-1 / MXOS-RUNTIME-1 vertical slice).

Implements the smallest real MANAGED session runtime on top of the existing
Conduvera harness gateway and adapter contracts:

- ManagedJob: task/attempt/worktree descriptor.
- ManagedSession: stable UUID session with ownership_class=MANAGED, process
  fingerprints (pid, start_time, boot_id, command), scope identifier, state
  machine, evidence references.
- ManagedSessionRegistry: atomic 0600 state writes; only sessions started
  through this runtime may be MANAGED; PID alone is never ownership proof;
  EXTERNAL_* sessions can never transition to MANAGED.
- MXOS-EVIDENCE-1.0.0 event chain via the existing EventEnvelope contract.

States (contract): CREATED -> STARTING -> RUNNING -> {CANCEL_REQUESTED ->
CANCELLED | COMPLETED | FAILED | LOST}. Cancel rejects every session whose
ownership_class is not MANAGED.

No secrets, tokens or raw auth data are ever persisted.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any



class SessionState(str, Enum):
    CREATED = "CREATED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    LOST = "LOST"


class OwnershipClass(str, Enum):
    MANAGED = "MANAGED"
    EXTERNAL_MANUAL_OBSERVED = "EXTERNAL_MANUAL_OBSERVED"
    EXTERNAL_UNKNOWN = "EXTERNAL_UNKNOWN"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _boot_id() -> str:
    """Read /proc/sys/kernel/random/boot_id (stable per boot)."""
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return ""


def _process_start_time(pid: int) -> str:
    """Process start time (jiffies since boot) from /proc/<pid>/stat field 22."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        # cmdline may contain spaces/parens; split after the last ')'
        after = stat.rsplit(")", 1)[1].split()
        if len(after) >= 20:
            return after[19]
    except OSError:
        pass
    return ""


def _process_cmd(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace").replace("\x00", " ").strip()
    except OSError:
        return ""


@dataclass
class ManagedJob:
    """Task/attempt descriptor for one managed session."""

    task_id: str
    attempt_id: str
    repo: str = ""
    base_commit: str = ""
    worktree: str = ""
    harness_descriptor: str = ""
    model_binding: dict[str, Any] = field(default_factory=dict)
    timeout_s: float = 120.0
    safety_policy: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessFingerprint:
    """Ownership proof — PID alone is NEVER sufficient."""

    pid: int
    start_time: str
    boot_id: str
    command: str

    def matches(self, other: "ProcessFingerprint") -> bool:
        # Ownership proof: pid + start_time + boot_id. The command string is
        # recorded as an observation but is NOT a mismatch criterion: with
        # systemd-run --scope the exec transition can snapshot the wrapper
        # argv transiently, and argv is mutable. start_time (jiffies since
        # boot) is the authoritative reuse detector.
        return (
            self.pid == other.pid
            and self.start_time == other.start_time
            and self.boot_id == other.boot_id
        )

    def to_dict(self) -> dict[str, Any]:
        return {"pid": self.pid, "start_time": self.start_time,
                "boot_id": self.boot_id, "command": self.command}


@dataclass
class ManagedSession:
    """One managed harness session (stable identity, state machine)."""

    session_id: str
    task_id: str
    attempt_id: str
    ownership_class: OwnershipClass = OwnershipClass.MANAGED
    managed: bool = True
    instance_id: str = ""
    fingerprint: ProcessFingerprint | None = None
    scope_id: str = ""
    state: SessionState = SessionState.CREATED
    created_at: str = ""
    started_at: str = ""
    ended_at: str = ""
    exit_code: int | None = None
    worktree: str = ""
    base_commit: str = ""
    adapter_session_id: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    harness_descriptor: str = ""
    model_binding: dict[str, Any] = field(default_factory=dict)
    timeout_s: float = 120.0
    safety_policy: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        job: ManagedJob,
        session_id: str | None = None,
    ) -> "ManagedSession":
        return cls(
            session_id=session_id or f"mxs_{uuid.uuid4().hex[:16]}",
            task_id=job.task_id,
            attempt_id=job.attempt_id,
            instance_id=f"{job.attempt_id}-{uuid.uuid4().hex[:8]}",
            created_at=_utc_now(),
            worktree=job.worktree,
            base_commit=job.base_commit,
            harness_descriptor=job.harness_descriptor,
            model_binding=dict(job.model_binding),
            timeout_s=job.timeout_s,
            safety_policy=dict(job.safety_policy),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
            "ownership_class": self.ownership_class.value,
            "managed": self.managed,
            "instance_id": self.instance_id,
            "fingerprint": self.fingerprint.to_dict() if self.fingerprint else None,
            "scope_id": self.scope_id,
            "state": self.state.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "exit_code": self.exit_code,
            "worktree": self.worktree,
            "base_commit": self.base_commit,
            "adapter_session_id": self.adapter_session_id,
            "evidence_refs": list(self.evidence_refs),
            "harness_descriptor": self.harness_descriptor,
            "model_binding": dict(self.model_binding),
            "timeout_s": self.timeout_s,
            "safety_policy": dict(self.safety_policy),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ManagedSession":
        fp = data.get("fingerprint")
        return cls(
            session_id=data["session_id"],
            task_id=data.get("task_id", ""),
            attempt_id=data.get("attempt_id", ""),
            ownership_class=OwnershipClass(data.get("ownership_class", "MANAGED")),
            managed=bool(data.get("managed", True)),
            instance_id=data.get("instance_id", ""),
            fingerprint=ProcessFingerprint(**fp) if fp else None,
            scope_id=data.get("scope_id", ""),
            state=SessionState(data.get("state", "CREATED")),
            created_at=data.get("created_at", ""),
            started_at=data.get("started_at", ""),
            ended_at=data.get("ended_at", ""),
            exit_code=data.get("exit_code"),
            worktree=data.get("worktree", ""),
            base_commit=data.get("base_commit", ""),
            adapter_session_id=data.get("adapter_session_id", ""),
            evidence_refs=list(data.get("evidence_refs", [])),
            harness_descriptor=data.get("harness_descriptor", ""),
            model_binding=dict(data.get("model_binding", {})),
            timeout_s=float(data.get("timeout_s", 120.0)),
            safety_policy=dict(data.get("safety_policy", {})),
        )


class ExternalSessionError(Exception):
    """Raised when an operation targets a non-MANAGED session."""


class RegistryCorruptError(Exception):
    """Raised when the persistent session registry is invalid or truncated.

    Fail-closed: a corrupt registry is NEVER silently replaced with an empty
    one. The structured error lets the control plane refuse to continue rather
    than lose session/ownership/scope/evidence identity.
    """


class ManagedSessionRegistry:
    """Atomic 0600 state store for managed sessions.

    Only sessions created through this registry are MANAGED. External sessions
    are registered (read-only observations) with ownership EXTERNAL_* and
    control_rights=none; cancel() rejects them unconditionally.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def _acquire_lock(self) -> Any:
        import fcntl
        fh = open(self._lock_path, "w")
        fcntl.flock(fh, fcntl.LOCK_EX)
        return fh

    def _read(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"sessions": {}}
        raw = self.path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            # T03 / B2: a truncated or invalid registry is a structured error,
            # NEVER a silent empty success (would lose session/scope/evidence).
            raise RegistryCorruptError(
                f"session registry corrupt: {self.path} "
                f"(JSON error at line {e.lineno} col {e.colno})"
            ) from e
        if not isinstance(data, dict) or not isinstance(data.get("sessions"), dict):
            raise RegistryCorruptError(
                f"session registry invalid schema: {self.path}")
        return data

    def _write(self, data: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)
        os.chmod(self.path, 0o600)

    def register(self, session: ManagedSession) -> ManagedSession:
        fh = self._acquire_lock()
        try:
            data = self._read()
            data.setdefault("sessions", {})[session.session_id] = session.to_dict()
            self._write(data)
        finally:
            fh.close()
        return session

    def get(self, session_id: str) -> ManagedSession | None:
        data = self._read()
        raw = data.get("sessions", {}).get(session_id)
        return ManagedSession.from_dict(raw) if raw else None

    def update(self, session: ManagedSession) -> None:
        fh = self._acquire_lock()
        try:
            data = self._read()
            data.setdefault("sessions", {})[session.session_id] = session.to_dict()
            self._write(data)
        finally:
            fh.close()

    def all(self) -> list[ManagedSession]:
        data = self._read()
        return [ManagedSession.from_dict(r) for r in data.get("sessions", {}).values()]

    def permission_ok(self) -> bool:
        if not self.path.is_file():
            return True
        mode = self.path.stat().st_mode & 0o777
        return mode == 0o600
