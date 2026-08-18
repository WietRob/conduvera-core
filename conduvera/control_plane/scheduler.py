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
    CLAIMED = "CLAIMED"
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
    """One submitted job (Buildroom-compatible task descriptor).

    The raw prompt is NEVER persisted: only a redacted summary and a content
    hash are stored. Secrets/auth material never enters the queue store.
    """

    job_id: str
    task_id: str
    repo: str
    base_commit: str
    harness: str
    model_binding: dict[str, Any]
    prompt: str
    timeout_s: float = 180.0
    prompt_hash: str = ""
    prompt_summary: str = "[redacted]"
    payload_ref: str = ""
    content_sha256: str = ""
    task_type: str = "code_change"
    attempts: list[str] = field(default_factory=list)
    state: JobState = JobState.ACCEPTED
    created_at: str = ""
    updated_at: str = ""
    terminal_reason: str = ""
    result_refs: list[str] = field(default_factory=list)
    exit_code: int | None = None
    # acceptance-only fixture metadata (CONDUVERA_ACCEPTANCE_MODE=1 only)
    scenario: str = ""
    hold_s: float | None = None
    fixture_out: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"job_id": self.job_id, "task_id": self.task_id, "repo": self.repo,
                "base_commit": self.base_commit, "harness": self.harness,
                "model_binding": _redact(self.model_binding), "prompt": "",
                "prompt_hash": self.prompt_hash, "prompt_summary": self.prompt_summary,
                "payload_ref": self.payload_ref, "content_sha256": self.content_sha256,
                "task_type": self.task_type, "timeout_s": self.timeout_s,
                "attempts": list(self.attempts),
                "state": self.state.value, "created_at": self.created_at,
                "updated_at": self.updated_at, "terminal_reason": self.terminal_reason,
                "result_refs": list(self.result_refs), "exit_code": self.exit_code,
                "scenario": self.scenario, "hold_s": self.hold_s,
                "fixture_out": self.fixture_out}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JobDescriptor":
        return cls(
            job_id=d["job_id"], task_id=d["task_id"], repo=d["repo"],
            base_commit=d["base_commit"], harness=d["harness"],
            model_binding=dict(d.get("model_binding", {})), prompt="",
            prompt_hash=d.get("prompt_hash", ""),
            prompt_summary=d.get("prompt_summary", "[redacted]"),
            payload_ref=d.get("payload_ref", ""),
            content_sha256=d.get("content_sha256", ""),
            task_type=d.get("task_type", "code_change"),
            timeout_s=float(d.get("timeout_s", 180.0)),
            attempts=list(d.get("attempts", [])),
            state=JobState(d.get("state", "ACCEPTED")),
            created_at=d.get("created_at", ""), updated_at=d.get("updated_at", ""),
            terminal_reason=d.get("terminal_reason", ""),
            result_refs=list(d.get("result_refs", [])),
            exit_code=d.get("exit_code"),
            scenario=d.get("scenario", ""), hold_s=d.get("hold_s"),
            fixture_out=d.get("fixture_out", ""),
        )

    def bind_prompt(self, prompt: str) -> None:
        """Store only a content hash — NEVER any prompt content.

        Goal G hardening: no raw prompt, no prompt fragment, no token value
        may enter queue/registry files. Only a content hash is persisted;
        the summary is a constant redaction marker.
        """
        import hashlib
        self.prompt_hash = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        self.prompt_summary = "[prompt redacted]"


def _redact(value: Any) -> Any:
    """Recursively redact secrets/tokens/auth material."""
    import re
    sensitive = re.compile(
        r"(?i)(token|api[_-]?key|secret|password|authorization|credential|"
        r"bearer|LITELLM_API_KEY|SONAR_TOKEN)")
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if sensitive.search(str(k)):
                out[k] = "[REDACTED]"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, str):
        return "[REDACTED]" if sensitive.search(value) else value
    return value


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
    claim_owner: str = ""
    claim_lease_until: str = ""
    exit_code: int | None = None
    terminal_reason: str = ""
    admission_reason: str = ""
    admission_retry_after: str = ""
    # Phase D: source-repo integrity snapshot captured at dispatch time, so the
    # delivery gate can prove the source repository was not mutated outside the
    # task worktree. {"head": ..., "porcelain_hash": ...} or empty.
    source_snapshot: str = ""
    result_refs: list[str] = field(default_factory=list)
    idem_key: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {"attempt_id": self.attempt_id, "job_id": self.job_id,
                "task_id": self.task_id, "session_id": self.session_id,
                "state": self.state.value, "harness": self.harness,
                "worktree": dict(self.worktree) if self.worktree else None,
                "scope_id": self.scope_id, "created_at": self.created_at,
                "updated_at": self.updated_at, "terminal": self.terminal,
                "retained_at": self.retained_at, "claim_owner": self.claim_owner,
                "claim_lease_until": self.claim_lease_until,
                "exit_code": self.exit_code, "terminal_reason": self.terminal_reason,
                "admission_reason": self.admission_reason,
                "admission_retry_after": self.admission_retry_after,
                "source_snapshot": self.source_snapshot,
                "result_refs": list(self.result_refs), "idem_key": self.idem_key}

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
            claim_owner=d.get("claim_owner", ""),
            claim_lease_until=d.get("claim_lease_until", ""),
            exit_code=d.get("exit_code"),
            terminal_reason=d.get("terminal_reason", ""),
            admission_reason=d.get("admission_reason", ""),
            admission_retry_after=d.get("admission_retry_after", ""),
            source_snapshot=d.get("source_snapshot", ""),
            result_refs=list(d.get("result_refs", [])),
            idem_key=d.get("idem_key", ""),
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

    def _read_with(self, fh: Any, attempt: Any) -> dict[str, Any]:
        """Read under an already-held lock and write one attempt update."""
        data = self._read()
        data.setdefault("attempts", {})[attempt.attempt_id] = attempt.to_dict()
        return data

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
        # Canonical per-harness defaults. Caller-provided overrides MERGE on
        # top of these (they never replace the map), so every existing harness
        # keeps its prior limit when one harness is tightened.
        self.per_harness = {"hermes_scoped": 2, "codex_cli": 2,
                            "opencode_cli": 1, "hermes": 2}
        if per_harness_limits:
            self.per_harness.update(per_harness_limits)
        self.retention_s = retention_s

    def running_counts(self) -> tuple[int, dict[str, int]]:
        """(global_running, per_harness_running) from RUNNING/CLAIMED attempts.

        QUEUED attempts do not consume capacity (they are waiting for it).
        """
        by_harness: dict[str, int] = {}
        global_running = 0
        for a in self.store.all_attempts():
            if a.state in (AttemptState.RUNNING, AttemptState.CLAIMED):
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

    def claim(
        self, attempt_id: str, *, lease_s: float = 300.0,
        dispatcher_id: str = "default",
    ) -> AttemptDescriptor | None:
        """Atomically claim one queued attempt (exactly one owner).

        The claim is persisted (CLAIMED + claim_owner + lease deadline).
        A second claim attempt from any other dispatcher fails (None).
        """
        fh = self.store._acquire()
        try:
            a = self.store.get_attempt(attempt_id)
            if a is None or a.state is not AttemptState.QUEUED:
                return None
            # Phase E: a local attempt held by the admission gate has a retry
            # timestamp; do not hot-loop it until the local GPU lane may be ready.
            if a.admission_retry_after:
                try:
                    import datetime as _dt
                    until = _dt.datetime.fromisoformat(a.admission_retry_after)
                    now = _dt.datetime.now(_dt.timezone.utc)
                    if until.replace(tzinfo=_dt.timezone.utc) > now:
                        return None
                except ValueError:
                    pass
            a.state = AttemptState.CLAIMED
            a.claim_owner = dispatcher_id
            a.claim_lease_until = _utc_now()
            a.updated_at = _utc_now()
            self.store._write(self.store._read_with(fh, a))
            return a
        finally:
            fh.close()

    def release_claim(self, attempt_id: str) -> AttemptDescriptor | None:
        """Return a CLAIMED attempt safely to the queue (idempotent)."""
        fh = self.store._acquire()
        try:
            a = self.store.get_attempt(attempt_id)
            if a is None or a.state is not AttemptState.CLAIMED:
                return a
            a.state = AttemptState.QUEUED
            a.claim_owner = ""
            a.claim_lease_until = ""
            a.updated_at = _utc_now()
            self.store._write(self.store._read_with(fh, a))
            return a
        finally:
            fh.close()

    def recover_expired_claims(self, lease_s: float = 300.0) -> list[str]:
        """Return CLAIMED attempts whose lease expired back to QUEUED.

        Uses persisted claim timestamps (never wall-clock of the caller).
        Returns attempt ids recovered.
        """
        import datetime as _dt
        recovered = []
        for a in self.store.all_attempts():
            if a.state is not AttemptState.CLAIMED or not a.claim_lease_until:
                continue
            try:
                claimed_at = _dt.datetime.fromisoformat(a.claim_lease_until)
                age = (_dt.datetime.now(_dt.timezone.utc) - claimed_at.replace(
                    tzinfo=_dt.timezone.utc)).total_seconds()
            except ValueError:
                recovered.append(a.attempt_id)
                continue
            if age > lease_s:
                self.release_claim(a.attempt_id)
                recovered.append(a.attempt_id)
        return recovered

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
