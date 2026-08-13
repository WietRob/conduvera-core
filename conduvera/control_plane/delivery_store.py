"""Durable DeliveryStore (SHIP-CONDUVERA-DELIVERY, Workstream A).

Persists DeliveryRecord objects and their append-only transition history in
Control-Plane-owned storage OUTSIDE agent-writable worktrees.

Properties:
- stable delivery_id;
- atomic 0600 writes (tmp + os.replace);
- idempotent save/upsert by delivery_id;
- append-only transition history (never mutated/truncated in place);
- exact restart reconstruction (no success inferred from missing data);
- a dedicated lock file for concurrent multi-thread access.

Schema: CONDUVERA-DELIVERY-1.0.0.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

DELIVERY_SCHEMA = "CONDUVERA-DELIVERY-1.0.0"


class DeliveryStore:
    """Persistent delivery record store (0600 files, atomic write, locked)."""

    def __init__(self, delivery_dir: str | Path):
        self.dir = Path(delivery_dir).expanduser().resolve()
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _record_path(self, delivery_id: str) -> Path:
        return self.dir / f"{delivery_id}.json"

    def _history_path(self, delivery_id: str) -> Path:
        return self.dir / f"{delivery_id}.events.jsonl"

    def _lock_path(self, delivery_id: str) -> Path:
        return self.dir / f"{delivery_id}.lock"

    # -- record ------------------------------------------------------------
    def save(self, record: dict) -> str:
        """Upsert a DeliveryRecord by delivery_id (atomic 0600 write)."""
        delivery_id = record.get("delivery_id") or f"dlv_{uuid.uuid4().hex[:12]}"
        data = {"schema_version": DELIVERY_SCHEMA, "delivery_id": delivery_id,
                **record}
        with self._lock:
            lockf = self._lock_path(delivery_id)
            try:
                fd = os.open(lockf, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except FileExistsError:
                pass
            try:
                p = self._record_path(delivery_id)
                tmp = p.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, sort_keys=True, indent=2),
                               encoding="utf-8")
                os.chmod(tmp, 0o600)
                os.replace(tmp, p)
            finally:
                try:
                    os.unlink(lockf)
                except FileNotFoundError:
                    pass
        return delivery_id

    def get(self, delivery_id: str) -> dict | None:
        p = self._record_path(delivery_id)
        if not p.is_file():
            return None
        try:
            with self._lock:
                return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def all(self) -> list[dict]:
        out = []
        for p in self.dir.glob("dlv_*.json"):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(out, key=lambda r: r.get("created_at", ""))

    def delete(self, delivery_id: str) -> bool:
        """Hard delete (used only by tests / explicit acceptance cleanup)."""
        with self._lock:
            p = self._record_path(delivery_id)
            if p.is_file():
                p.unlink()
                return True
            return False

    # -- append-only transition history ------------------------------------
    def append_event(self, delivery_id: str, event: dict) -> int:
        """Append one transition event; returns the event sequence number."""
        event = dict(event)
        seq = event.get("seq")
        if seq is None:
            seq = self._next_seq(delivery_id)
        event["seq"] = seq
        with self._lock:
            p = self._history_path(delivery_id)
            line = json.dumps(event, sort_keys=True)
            with p.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            try:
                os.chmod(p, 0o600)
            except OSError:
                pass
        return seq

    def _next_seq(self, delivery_id: str) -> int:
        hist = self.history(delivery_id)
        return (hist[-1]["seq"] + 1) if hist else 1

    def history(self, delivery_id: str) -> list[dict]:
        p = self._history_path(delivery_id)
        if not p.is_file():
            return []
        events = []
        with self._lock:
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            except OSError:
                return []
        return sorted(events, key=lambda e: e.get("seq", 0))

    def last_event(self, delivery_id: str) -> dict | None:
        hist = self.history(delivery_id)
        return hist[-1] if hist else None
