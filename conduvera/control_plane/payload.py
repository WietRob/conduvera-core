"""Durable task-payload store (DURABLE-CODE-CHANGE-V1).

Replaces any in-memory-only prompt/task transport. The full task payload is
persisted under the state directory; queue/registry/outbox only ever hold a
payload_ref + content_sha256. On dispatch the payload is reloaded from the
persistent store, its content hash verified, and the exact original
instructions are passed to the harness.

Design:
- TaskPayloadEnvelope: full task descriptor (never raw secrets — only
  secret_refs).
- state directory mode 0700; payload files mode 0600.
- atomic temp-write + fsync + rename; writer lock.
- content hash verified before dispatch; missing/corrupt/hash-mismatched
  payload fails the attempt loudly (no empty/redacted fallback).
- deterministic, idempotent cleanup/retention.
- a memory cache is only an optimization over this persistent authority.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class PayloadError(Exception):
    """Base error for the payload store."""


class PayloadMissingError(PayloadError):
    """Referenced payload does not exist."""


class PayloadCorruptError(PayloadError):
    """Payload is corrupt or hash-mismatched."""


class TaskPayloadEnvelope:
    """Persisted task payload (never holds secret values, only refs)."""

    def __init__(
        self,
        *,
        payload_id: str,
        task_type: str,
        instructions: str,
        repo: str,
        base_commit: str,
        expected_artifacts: list[str] | None = None,
        test_plan: str = "",
        secret_refs: dict[str, str] | None = None,
        created_at: str | None = None,
        retention_until: str | None = None,
        content_sha256: str = "",
        schema_version: str = "task-payload.v1",
    ) -> None:
        self.payload_id = payload_id
        self.schema_version = schema_version
        self.task_type = task_type
        self.instructions = instructions
        self.repo = repo
        self.base_commit = base_commit
        self.expected_artifacts = list(expected_artifacts or [])
        self.test_plan = test_plan
        self.secret_refs = dict(secret_refs or {})
        self.created_at = created_at or _utc_now()
        self.retention_until = retention_until or _utc_now()
        self.content_sha256 = content_sha256 or _sha256(instructions)

    def verify(self) -> bool:
        """Content hash verification of the executable instructions."""
        return _sha256(self.instructions) == self.content_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "payload_id": self.payload_id,
            "schema_version": self.schema_version,
            "task_type": self.task_type,
            "instructions": self.instructions,
            "repo": self.repo,
            "base_commit": self.base_commit,
            "expected_artifacts": list(self.expected_artifacts),
            "test_plan": self.test_plan,
            "secret_refs": dict(self.secret_refs),
            "created_at": self.created_at,
            "retention_until": self.retention_until,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TaskPayloadEnvelope":
        return cls(
            payload_id=d["payload_id"],
            schema_version=d.get("schema_version", "task-payload.v1"),
            task_type=d.get("task_type", "code_change"),
            instructions=d.get("instructions", ""),
            repo=d.get("repo", ""),
            base_commit=d.get("base_commit", ""),
            expected_artifacts=list(d.get("expected_artifacts", [])),
            test_plan=d.get("test_plan", ""),
            secret_refs=dict(d.get("secret_refs", {})),
            created_at=d.get("created_at"),
            retention_until=d.get("retention_until"),
            content_sha256=d.get("content_sha256", ""),
        )


class TaskPayloadStore:
    """Persistent store for task payloads (atomic, locked, 0600/0700)."""

    def __init__(self, state_dir: str | Path) -> None:
        self.root = Path(state_dir).expanduser()
        self.payload_dir = self.root / "payloads"
        self.payload_dir.mkdir(parents=True, exist_ok=True)
        # state directory + payload directory are 0700
        self.root.chmod(0o700)
        self.payload_dir.chmod(0o700)

    def _lock(self) -> Any:
        lock_path = self.payload_dir / ".lock"
        fh = open(lock_path, "a+")  # noqa: SIM115
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        return fh

    def _unlock(self, fh: Any) -> None:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()

    def _path(self, payload_id: str) -> Path:
        safe = "".join(c for c in payload_id if c.isalnum() or c in "-_")
        return self.payload_dir / f"{safe}.json"

    def put(
        self,
        envelope: TaskPayloadEnvelope,
        *,
        retention_hours: float = 24.0,
    ) -> str:
        """Persist a payload atomically. Returns payload_id."""
        if not envelope.content_sha256:
            envelope.content_sha256 = _sha256(envelope.instructions)
        now = datetime.now(timezone.utc)
        envelope.created_at = now.isoformat()
        envelope.retention_until = (now + timedelta(hours=retention_hours)).isoformat()
        path = self._path(envelope.payload_id)
        fh = self._lock()
        try:
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(envelope.to_dict(), indent=2, ensure_ascii=False),
                           encoding="utf-8")
            tmp.chmod(0o600)
            with open(tmp, "ab") as f:
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
            path.chmod(0o600)
        finally:
            self._unlock(fh)
        return envelope.payload_id

    def get(self, payload_id: str) -> TaskPayloadEnvelope:
        """Load + hash-verify a payload. Missing/corrupt fails loudly."""
        path = self._path(payload_id)
        if not path.is_file():
            raise PayloadMissingError(f"payload {payload_id} missing")
        fh = self._lock()
        try:
            raw = path.read_text(encoding="utf-8")
        finally:
            self._unlock(fh)
        try:
            env = TaskPayloadEnvelope.from_dict(json.loads(raw))
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            raise PayloadCorruptError(
                f"payload {payload_id} corrupt: {exc}") from exc
        if not env.verify():
            raise PayloadCorruptError(
                f"payload {payload_id} hash mismatch (content changed)")
        return env

    def delete(self, payload_id: str) -> None:
        """Idempotent terminal cleanup."""
        path = self._path(payload_id)
        if path.is_file():
            path.unlink()

    def cleanup_expired(self) -> int:
        """Idempotent retention cleanup. Returns number removed."""
        removed = 0
        now = datetime.now(timezone.utc)
        for p in self.payload_dir.glob("*.json"):
            try:
                env = TaskPayloadEnvelope.from_dict(json.loads(p.read_text()))
                if env.retention_until:
                    until = datetime.fromisoformat(env.retention_until)
                    if until < now:
                        p.unlink()
                        removed += 1
            except (json.JSONDecodeError, KeyError, ValueError):
                pass  # leave corrupt files for loud failure on access
        return removed

    def exists(self, payload_id: str) -> bool:
        return self._path(payload_id).is_file()

    @property
    def count(self) -> int:
        return sum(1 for _ in self.payload_dir.glob("*.json") if not _.name.startswith("."))


def new_payload_id() -> str:
    return f"pl_{uuid.uuid4().hex[:16]}"
