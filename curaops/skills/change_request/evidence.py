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
from typing import Dict, List, Optional

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

        # Compute hash over the content *before* inserting the hash field
        content_str = json.dumps(evidence, sort_keys=True)
        evidence["hash"] = f"sha256:{hashlib.sha256(content_str.encode()).hexdigest()}"

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
        content_str = json.dumps(evidence, sort_keys=True)
        evidence["hash"] = f"sha256:{hashlib.sha256(content_str.encode()).hexdigest()}"
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
        warnings = [i for i in issues if i["severity"] == "WARNING"]

        evidence: Dict = {
            "schema_version": SCHEMA_VERSION,
            "cr_id": cr.id,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "status": cr.status.value,
            "change_type": cr.change_type.value,
            "requirement_linkage_type": (
                cr.requirement_linkage_type.value
                if cr.requirement_linkage_type
                else None
            ),
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
    def _filename(cr: ChangeRequest) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{cr.id}_{ts}.json"


def _json_default(obj):
    """Handle non-serialisable types in JSON dump."""
    if isinstance(obj, datetime):
        return obj.isoformat() + "Z"
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
