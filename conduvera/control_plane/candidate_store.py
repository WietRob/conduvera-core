"""Immutable PublishCandidateStore (TRUSTED-FEATURE-DELIVERY, WS B).

Persists approved PublishCandidate manifests in Control-Plane-owned storage
(0600, atomic writes). Once a candidate is approved its manifest is immutable;
approval freezes it and publication consumes only candidate_id.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from pathlib import Path

_SCHEMA_VERSION = "CONDUVERA-PUBLISH-CANDIDATE-1.0.0"

_CANDIDATE_ID_RE = re.compile(r"^cand_[a-z0-9]{16,}$")


def sanitize_candidate_id(value: str) -> str:
    if not _CANDIDATE_ID_RE.match(value):
        raise ValueError("invalid candidate_id")
    return value


class PublishCandidateStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._idx_path = self.root / "index.json"
        self._index: dict[str, dict] = {}
        self._load_index()

    # -- index -------------------------------------------------------------
    def _load_index(self) -> None:
        if self._idx_path.is_file():
            try:
                self._index = json.loads(self._idx_path.read_text())
            except (json.JSONDecodeError, OSError):
                self._index = {}
        else:
            self._index = {}

    def _write_index(self) -> None:
        tmp = self._idx_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._index, sort_keys=True, indent=2))
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._idx_path)

    # -- crud --------------------------------------------------------------
    def put(self, candidate: dict) -> str:
        with self._lock:
            cid = candidate.get("candidate_id")
            if not cid:
                cid = f"cand_{uuid.uuid4().hex[:16]}"
                candidate["candidate_id"] = cid
            candidate["schema_version"] = _SCHEMA_VERSION
            path = self.root / f"{cid}.json"
            # atomic + 0600
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(candidate, sort_keys=True, indent=2))
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
            self._index[cid] = {
                "candidate_id": cid,
                "job_id": candidate.get("job_id"),
                "attempt_id": candidate.get("attempt_id"),
                "delivery_id": candidate.get("delivery_id"),
                "approved_at": candidate.get("approved_at"),
                "invalidated_at": candidate.get("invalidated_at"),
            }
            self._write_index()
            return cid

    def get(self, candidate_id: str) -> dict | None:
        cid = sanitize_candidate_id(candidate_id)
        path = self.root / f"{cid}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def all(self) -> list[dict]:
        out = []
        for cid in list(self._index):
            c = self.get(cid)
            if c is not None:
                out.append(c)
        return out

    def list_summary(self) -> list[dict]:
        return [dict(v) for v in self._index.values()]

    def find_by_job_attempt(self, job_id: str, attempt_id: str) -> dict | None:
        for c in self.all():
            if c.get("job_id") == job_id and c.get("attempt_id") == attempt_id:
                return c
        return None

    def invalidate(self, candidate_id: str, reason: str) -> dict | None:
        with self._lock:
            c = self.get(candidate_id)
            if c is None:
                return None
            c["invalidated_at"] = self._now()
            c["invalidation_reason"] = reason
            self.put(c)
            return c

    @staticmethod
    def _now() -> str:
        import datetime
        return datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
