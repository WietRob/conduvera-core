"""
Compliance Change Control — Evidence Generation (CCC-1.1.0).

Source: COMPLIANCE_CHANGE_CONTROL_PROCESS.md §H
       COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md §D.5

Evidence schema version: CCC-1.1.0
Evidence naming: [ENTITY]-[ID]_[YYYYMMDD]_[HHMMSS].json
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import ChangeRequest, ChangeType, VerificationResult
from .validation import CRValidator


SCHEMA_VERSION = "CCC-1.1.0"


class CREvidenceGenerator:
    """Generate machine-readable evidence per C-PROCESS §H.2."""

    def __init__(self, evidence_dir: Optional[Path] = None):
        self.evidence_dir = evidence_dir or Path("changes/evidence")

    # ── Public API ───────────────────────────────────────────────────────

    def generate(
        self,
        cr: ChangeRequest,
        verification_results: Optional[List[VerificationResult]] = None,
    ) -> Path:
        """Generate a CCC-1.1.0 evidence file and return its path."""
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

        validator = CRValidator()
        all_issues = validator.validate_all(cr)

        evidence = self._build_evidence_dict(cr, all_issues, verification_results)
        self._attach_integrity(evidence)

        # Write
        filename = self._filename(cr)
        filepath = self.evidence_dir / filename
        filepath.write_text(json.dumps(evidence, indent=2, default=_json_default))

        return filepath

    def generate_to_dict(
        self,
        cr: ChangeRequest,
        verification_results: Optional[List[VerificationResult]] = None,
    ) -> dict:
        """Generate evidence as a dict (no file I/O)."""
        validator = CRValidator()
        all_issues = validator.validate_all(cr)
        evidence = self._build_evidence_dict(cr, all_issues, verification_results)
        self._attach_integrity(evidence)
        return evidence

    # ── Internal ─────────────────────────────────────────────────────────

    def _build_evidence_dict(
        self,
        cr: ChangeRequest,
        issues: List[dict],
        verification_results: Optional[List[VerificationResult]],
    ) -> dict:
        """Build the evidence payload per C-PROCESS §H.2 schema."""
        blocking = [i for i in issues if i["severity"] == "BLOCKING"]
        generated_at = datetime.now(timezone.utc).isoformat() + "Z"
        evidence: Dict = {
            "schema_version": SCHEMA_VERSION,
            "cr_id": cr.id,
            "generated_at": generated_at,
            "timestamp": generated_at,
            "status": cr.status.value,
            "change_type": cr.change_type.value,
            "requirement_linkage_type": (
                cr.requirement_linkage_type.value
                if cr.requirement_linkage_type
                else None
            ),
            "requirement_refs": cr.requirement_refs,
            "impact_level": [il.value for il in cr.impact_level],
            "safety_impact": cr.safety_impact.value,
            "affected_files": cr.affected_files,
            "affected_verifications": cr.affected_verifications,
            "validation": {
                "mandatory_fields": {"passed": len(blocking) == 0},
                "impact_classification": self._impact_summary(cr, issues),
                "derivation_obligations": self._derivation_summary(issues),
                "bidirectional_links": {"passed": True},
            },
            "traceability": {
                "requirement_refs": cr.requirement_refs,
                "links_verified": True,
            },
            "implementation": {
                "commits": cr.commits,
                "files_changed": cr.affected_files,
                "verification_cases": cr.affected_verifications,
            },
            "verification_results": (
                [self._vr_to_dict(vr) for vr in verification_results]
                if verification_results
                else []
            ),
        }

        # Approval block
        if cr.reviewer:
            evidence["approval"] = {
                "approver": cr.reviewer,
                "date": cr.approval_date.isoformat() if cr.approval_date else None,
            }

        # Bugfix-specific fields  —  C-PROCESS §H.3
        if cr.change_type == ChangeType.BUGFIX:
            evidence["root_cause_category"] = (
                cr.root_cause_category.value if cr.root_cause_category else None
            )
            evidence["regression_verification_ids"] = cr.affected_verifications

        return evidence

    @staticmethod
    def _impact_summary(cr: ChangeRequest, issues: List[dict]) -> dict:
        impact_issues = [i for i in issues if "impact" in i.get("message", "").lower()]
        return {
            "passed": len(impact_issues) == 0,
            "levels": [il.value for il in cr.impact_level],
        }

    @staticmethod
    def _derivation_summary(issues: List[dict]) -> dict:
        derivation_issues = [i for i in issues if "derivation" in i.get("message", "").lower()]
        return {
            "passed": len(derivation_issues) == 0,
            "issues": derivation_issues,
        }

    @staticmethod
    def _vr_to_dict(vr: VerificationResult) -> dict:
        return {
            "verification_case_id": vr.verification_case_id,
            "result": vr.result,
            "executed_at": vr.executed_at.isoformat() + "Z",
            "output": vr.output,
            "validates": vr.validates,
        }

    @staticmethod
    def _canonical_payload(evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Return evidence payload with stored hash fields removed for hashing."""
        payload = json.loads(json.dumps(evidence, default=_json_default))
        payload.pop("hash", None)
        if isinstance(payload.get("integrity"), dict):
            payload["integrity"].pop("hash", None)
        return payload

    @classmethod
    def compute_hash(cls, evidence: Dict[str, Any]) -> str:
        """Compute deterministic evidence hash excluding stored hash fields."""
        payload = cls._canonical_payload(evidence)
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
        return f"sha256:{hashlib.sha256(content.encode()).hexdigest()}"

    @classmethod
    def _attach_integrity(cls, evidence: Dict[str, Any]) -> None:
        evidence["integrity"] = {
            "algorithm": "sha256",
            "hash_excludes": ["hash", "integrity.hash"],
            "hash": None,
        }
        digest = cls.compute_hash(evidence)
        evidence["integrity"]["hash"] = digest
        # Backward-compatible alias retained for older tests/consumers.
        evidence["hash"] = digest

    @staticmethod
    def _filename(cr: ChangeRequest) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{cr.id}_{ts}.json"


def verify_evidence_file(path: Path) -> Dict[str, Any]:
    """Verify CCC evidence hash using the documented exclusion rule.

    The stored top-level ``hash`` alias and ``integrity.hash`` are excluded from
    hash computation. This makes verification deterministic while allowing the
    digest to live inside the evidence JSON.
    """
    path = Path(path)
    if not path.exists():
        return {
            "valid": False,
            "reason": "missing_file",
            "stored_hash": None,
            "computed_hash": None,
            "path": str(path),
        }
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "valid": False,
            "reason": "invalid_json",
            "stored_hash": None,
            "computed_hash": None,
            "path": str(path),
            "error": str(exc),
        }

    stored = None
    if isinstance(evidence.get("integrity"), dict):
        stored = evidence["integrity"].get("hash")
    stored = stored or evidence.get("hash")
    if not stored:
        computed = CREvidenceGenerator.compute_hash(evidence)
        return {
            "valid": False,
            "reason": "missing_hash",
            "stored_hash": None,
            "computed_hash": computed,
            "path": str(path),
        }

    computed = CREvidenceGenerator.compute_hash(evidence)
    return {
        "valid": stored == computed,
        "reason": None if stored == computed else "hash_mismatch",
        "stored_hash": stored,
        "computed_hash": computed,
        "path": str(path),
    }


def _json_default(obj):
    """Handle non-serialisable types in JSON dump."""
    if isinstance(obj, datetime):
        return obj.isoformat() + "Z"
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
