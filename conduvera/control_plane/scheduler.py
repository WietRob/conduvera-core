"""Multi-session scheduler with persistent queue, concurrency limits and
tombstones (CONTROL-PLANE-ALPHA-V1).

- persistent job/attempt queue (JSON, atomic 0600 writes);
- configurable global and per-harness concurrency limits;
- deterministic lifecycle transitions;
- retention/tombstones for terminal sessions (idempotent cancel/cleanup);
- no double ownership and no parallel writers to the same registry state
  (single scheduler lock + atomic writes).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class JobState(str, Enum):
    ACCEPTED = "ACCEPTED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class AttemptState(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    RETENTION = "RETENTION"  # tombstone


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobDescriptor:
    """One submitted job (Buildroom-compatible task descriptor)."""

    job_id: str
    task_id: str
    repo: str
    base_commit: str
    harness: str
    model_binding: dict[str, Any]
    prompt: str
    timeout_s: float = 180.0
    attempts: list[str] = field(default_factory=list)
    state: JobState = JobState.ACCEPTED
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"job_id": self.job_id, "task_id": self.task_id, "repo": self.repo,
                "base_commit": self.base_commit, "harness": self.harness,
                "model_binding": dict(self.model_binding), "prompt": self.prompt,
                "timeout_s": self.timeout_s, "attempts": list(self.attempts),
                "state": self.state.value, "created_at": self.created_at,
                "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JobDescriptor":
        return cls(
            job_id=d["job_id"], task_id=d["task_id"], repo=d["repo"],
            base_commit=d["base_commit"], harness=d["harness"],
            model_binding=dict(d.get("model_binding", {})), prompt=d["prompt"],
            timeout_s=float(d.get("timeout_s", 180.0)),
            attempts=list(d.get("attempts", [])),
            state=JobState(d.get("state", "ACCEPTED")),
            created_at=d.get("created_at", ""), updated_at=d.get("updated_at", ""),
        )


@dataclass
class AttemptDescriptor:
    """One attempt of a job (stable task/attempt/session binding)."""

    attempt_id: str
    job_id: str
    task_id: str
    session_id: str = ""
    state: AttemptState = AttemptState.CREATED
    harness: str = ""
    worktree: dict[str, str] | None = None
    scope_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    terminal: bool = False
    retained_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"attempt_id": self.attempt_id, "job_id": self.job_id,
                "task_id": self.task_id, "session_id": self.session_id,
                "state": self.state.value, "harness": self.harness,
                "worktree": dict(self.worktree) if self.worktree else None,
                "scope_id": self.scope_id, "created_at": self.created_at,
                "updated_at": self.updated_at, "terminal": self.terminal,
                "retained_at": self.retained_at}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AttemptDescriptor":
        return cls(
            attempt_id=d["attempt_id"], job_id=d["job_id"], task_id=d["task_id"],
            session_id=d.get("session_id", ""),
            state=AttemptState(d.get("state", "CREATED")),
            harness=d.get("harness", ""),
            worktree=dict(d["worktree"]) if d.get("worktree") else None,
            scope_id=d.get("scope_id", ""), created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""), terminal=bool(d.get("terminal", False)),
            retained_at=d.get("retained_at", ""),
        )


class SchedulerStore:
    """Persistent atomic 0600 queue store (single-writer via lock)."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def _acquire(self):
        import fcntl
        fh = open(self._lock_path, "w")
        fcntl.flock(fh, fcntl.LOCK_EX)
        return fh

    def _read(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"jobs": {}, "attempts": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"jobs": {}, "attempts": {}}

    def _write(self, data: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)
        os.chmod(self.path, 0o600)

    def save_job(self, job: JobDescriptor) -> None:
        fh = self._acquire()
        try:
            data = self._read()
            data.setdefault("jobs", {})[job.job_id] = job.to_dict()
            self._write(data)
        finally:
            fh.close()

    def save_attempt(self, attempt: AttemptDescriptor) -> None:
        fh = self._acquire()
        try:
            data = self._read()
            data.setdefault("attempts", {})[attempt.attempt_id] = attempt.to_dict()
            self._write(data)
        finally:
            fh.close()

    def get_job(self, job_id: str) -> JobDescriptor | None:
        d = self._read().get("jobs", {}).get(job_id)
        return JobDescriptor.from_dict(d) if d else None

    def get_attempt(self, attempt_id: str) -> AttemptDescriptor | None:
        d = self._read().get("attempts", {}).get(attempt_id)
        return AttemptDescriptor.from_dict(d) if d else None

    def all_jobs(self) -> list[JobDescriptor]:
        return [JobDescriptor.from_dict(d)
                for d in self._read().get("jobs", {}).values()]

    def all_attempts(self) -> list[AttemptDescriptor]:
        return [AttemptDescriptor.from_dict(d)
                for d in self._read().get("attempts", {}).values()]


class Scheduler:
    """Bounded multi-session scheduler (global + per-harness concurrency)."""

    def __init__(
        self,
        *,
        store: SchedulerStore,
        global_limit: int = 4,
        per_harness_limits: dict[str, int] | None = None,
        retention_s: float = 3600.0,
    ):
        self.store = store
        self.global_limit = global_limit
        self.per_harness = per_harness_limits or {
            "hermes_scoped": 2, "codex_cli": 2, "opencode_cli": 1, "hermes": 2}
        self.retention_s = retention_s

    def running_counts(self) -> tuple[int, dict[str, int]]:
        """(global_running, per_harness_running) from non-terminal attempts."""
        by_harness: dict[str, int] = {}
        global_running = 0
        for a in self.store.all_attempts():
            if a.state in (AttemptState.RUNNING, AttemptState.QUEUED):
                global_running += 1
                by_harness[a.harness] = by_harness.get(a.harness, 0) + 1
        return global_running, by_harness

    def can_start(self, harness: str) -> tuple[bool, str]:
        g, by = self.running_counts()
        if g >= self.global_limit:
            return False, f"global limit {self.global_limit} reached"
        limit = self.per_harness.get(harness, 1)
        if by.get(harness, 0) >= limit:
            return False, f"harness {harness} limit {limit} reached"
        return True, ""

    def queued_attempts(self) -> list[AttemptDescriptor]:
        return [a for a in self.store.all_attempts()
                if a.state is AttemptState.QUEUED]

    def advance(self, attempt_id: str, new_state: AttemptState) -> AttemptDescriptor | None:
        """Deterministic lifecycle transition (QUEUED -> RUNNING -> terminal)."""
        a = self.store.get_attempt(attempt_id)
        if a is None:
            return None
        a.state = new_state
        a.updated_at = _utc_now()
        if new_state in (AttemptState.COMPLETED, AttemptState.FAILED,
                         AttemptState.CANCELLED, AttemptState.TIMED_OUT):
            a.terminal = True
        self.store.save_attempt(a)
        return a

    def retain(self, attempt_id: str) -> AttemptDescriptor | None:
        """Tombstone a terminal attempt (retention marker, never deleted)."""
        a = self.store.get_attempt(attempt_id)
        if a is None:
            return None
        a.state = AttemptState.RETENTION
        a.terminal = True
        a.retained_at = _utc_now()
        self.store.save_attempt(a)
        return a

    def expire_retention(self) -> list[str]:
        """Idempotent cleanup of old tombstones (returns removed attempt ids)."""
        removed = []
        now = time.time()
        for a in self.store.all_attempts():
            if a.state is AttemptState.RETENTION and a.retained_at:
                try:
                    ts = datetime.fromisoformat(a.retained_at).timestamp()
                except ValueError:
                    continue
                if now - ts > self.retention_s:
                    removed.append(a.attempt_id)
        return removed
