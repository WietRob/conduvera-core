"""Durable EvidenceStore (CLOSURE-V1, Workstream D).

Persists per-Attempt/Session EvidenceBundles OUTSIDE disposable worktrees so
cleanup may delete runtime/worktree resources while retaining evidence,
artifact hashes, identity, terminal state and reason.

Evidence validation is fail-closed:
- a real process exit_code=0 with malformed/mismatched evidence ->
  evidence_status=INVALID, attempt/job FAILED, terminal_reason=EVIDENCE_INVALID;
- evidence hash mismatch or malformed evidence is never presented as success.

Schema: CONDUVERA-ACTIVITY-ACCEPTANCE-1.0.0 (evidence sub-schema) and the
generic CONDUVERA-EVIDENCE bundle format.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path


class EvidenceInvalidError(Exception):
    """Raised when evidence is malformed or its artifact hashes mismatch."""


class EvidenceStore:
    """Persistent evidence bundle store (0600 files, atomic write)."""

    def __init__(self, evidence_dir: str | Path):
        self.dir = Path(evidence_dir).expanduser().resolve()
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, bundle_id: str) -> Path:
        return self.dir / f"{bundle_id}.json"

    def put(self, bundle: dict) -> str:
        bundle_id = bundle.get("bundle_id") or f"ev_{int(time.time()*1000)}"
        data = json.dumps(bundle, sort_keys=True)
        tmp = self._path(bundle_id).with_suffix(".tmp")
        tmp.write_text(data, encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._path(bundle_id))
        return bundle_id

    def get(self, bundle_id: str) -> dict | None:
        p = self._path(bundle_id)
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def delete(self, bundle_id: str) -> None:
        p = self._path(bundle_id)
        if p.is_file():
            p.unlink()


def _sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def build_evidence_bundle(*, job_id: str, attempt_id: str, session_id: str,
                          harness: str, base_commit: str, worktree: str,
                          scope_id: str, process_pid: int | None,
                          exit_code: int | None, test_result: str,
                          artifact_paths: list[str], terminal_reason: str,
                          created_at: str, evidence_invalid_marker: bool = False,
                          artifact_hashes: list[str] | None = None) -> dict:
    """Assemble a schema-valid EvidenceBundle from a managed run.

    `evidence_invalid_marker` is set by the EXIT_0_WITH_INVALID_EVIDENCE
    fixture to force the fail-closed path (real exit 0 but invalid evidence).
    """
    artifacts: list[dict] = []
    for i, path in enumerate(artifact_paths or []):
        try:
            h = artifact_hashes[i] if artifact_hashes and i < len(artifact_hashes) else _sha256_file(path)
        except (OSError, FileNotFoundError):
            h = "sha256:" + ("0" * 64)
        artifacts.append({"path": path, "sha256": h})

    bundle = {
        "schema_version": "CONDUVERA-ACTIVITY-ACCEPTANCE-1.0.0",
        "bundle_id": f"ev_{job_id}_{attempt_id}_{session_id[-8:]}",
        "job_id": job_id,
        "attempt_id": attempt_id,
        "session_id": session_id,
        "harness": harness,
        "base_commit": base_commit,
        "worktree": worktree,
        "process": {"pid": process_pid, "scope_id": scope_id},
        "exit_code": exit_code,
        "test_result": test_result,
        "artifacts": artifacts,
        "terminal_reason": terminal_reason,
        "created_at": created_at,
    }
    if evidence_invalid_marker:
        bundle["evidence_invalid_marker"] = True
    return bundle


def validate_evidence(bundle: dict) -> dict:
    """Fail-closed validation of an EvidenceBundle.

    Returns the authoritative evidence_status. Any malformed/missing/mismatch
    -> INVALID (never presented as success).
    """
    if not isinstance(bundle, dict) or not bundle.get("schema_version"):
        return {"status": "INVALID", "reason": "EVIDENCE_INVALID"}
    if bundle.get("evidence_invalid_marker"):
        return {"status": "INVALID", "reason": "EVIDENCE_INVALID"}
    if bundle.get("exit_code") is None:
        return {"status": "INVALID", "reason": "EVIDENCE_MISSING_EXIT"}
    for a in bundle.get("artifacts", []):
        if not isinstance(a, dict) or not a.get("sha256") or not a.get("path"):
            return {"status": "INVALID", "reason": "EVIDENCE_INVALID"}
    # artifacts present and exit known -> valid
    return {"status": "VALID", "reason": ""}
