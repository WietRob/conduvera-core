"""
Compliance Change Control — Persistence (Markdown + JSON).

Source: COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md §F
       COMPLIANCE_CHANGE_CONTROL_PROCESS.md §B

CR storage:     changes/CR-[ID].md           (Markdown + YAML frontmatter)
VC storage:     verification/TC-{TYPE}-{Nr}.md
Evidence:       changes/evidence/CR-[ID]_[YYYYMMDD]_[HHMMSS].json
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .models import (
    ChangeRequest,
    ChangeType,
    CRStatus,
    ImpactLevel,
    RequirementLinkageType,
    RootCauseCategory,
    SafetyImpact,
    VerificationCase,
    VerificationStatus,
    VerificationType,
)


# ---------------------------------------------------------------------------
# ChangeRequest Persistence
# ---------------------------------------------------------------------------


class CRPersistence:
    """Read/write ChangeRequest as Markdown with YAML frontmatter."""

    def __init__(self, changes_dir: Optional[Path] = None):
        self.changes_dir = changes_dir or Path("changes")

    # ── Write ────────────────────────────────────────────────────────────

    def save(self, cr: ChangeRequest) -> Path:
        """Persist a ChangeRequest to disk. Returns the file path."""
        self.changes_dir.mkdir(parents=True, exist_ok=True)
        filepath = self.changes_dir / f"{cr.id}.md"

        frontmatter = _cr_to_frontmatter(cr)
        body = _cr_to_body(cr)

        content = f"---\n{yaml.dump(frontmatter, default_flow_style=False, sort_keys=False).strip()}\n---\n\n{body}"
        filepath.write_text(content, encoding="utf-8")
        cr.file_path = filepath
        return filepath

    # ── Read ─────────────────────────────────────────────────────────────

    def load(self, cr_id: str) -> ChangeRequest:
        """Load a ChangeRequest from disk."""
        filepath = self.changes_dir / f"{cr_id}.md"
        if not filepath.exists():
            raise FileNotFoundError(f"CR file not found: {filepath}")

        content = filepath.read_text(encoding="utf-8")
        fm = _parse_frontmatter(content)
        cr = _frontmatter_to_cr(fm, filepath)
        return cr

    def list_cr_ids(self) -> List[str]:
        """Return all CR IDs found in the changes directory."""
        if not self.changes_dir.exists():
            return []
        return sorted(
            f.stem for f in self.changes_dir.glob("CR-*.md")
        )

    def next_cr_number(self) -> int:
        """Determine the next CR sequence number."""
        existing = []
        for name in self.list_cr_ids():
            m = re.match(r"CR-(\d+)", name)
            if m:
                existing.append(int(m.group(1)))
        return max(existing, default=0) + 1


# ---------------------------------------------------------------------------
# VerificationCase Persistence
# ---------------------------------------------------------------------------


class VCPersistence:
    """Read/write VerificationCase as Markdown with YAML frontmatter."""

    def __init__(self, verification_dir: Optional[Path] = None):
        self.verification_dir = verification_dir or Path("verification")

    def save(self, vc: VerificationCase) -> Path:
        """Persist a VerificationCase to disk."""
        self.verification_dir.mkdir(parents=True, exist_ok=True)
        filepath = self.verification_dir / f"{vc.id}.md"

        frontmatter = _vc_to_frontmatter(vc)
        body = f"# {vc.id}: {vc.title}\n\n{vc.description}"

        content = f"---\n{yaml.dump(frontmatter, default_flow_style=False, sort_keys=False).strip()}\n---\n\n{body}"
        filepath.write_text(content, encoding="utf-8")
        vc.file_path = filepath
        return filepath

    def load(self, vc_id: str) -> VerificationCase:
        """Load a VerificationCase from disk."""
        filepath = self.verification_dir / f"{vc_id}.md"
        if not filepath.exists():
            raise FileNotFoundError(f"VerificationCase file not found: {filepath}")

        content = filepath.read_text(encoding="utf-8")
        fm = _parse_frontmatter(content)
        vc = _frontmatter_to_vc(fm, filepath)
        return vc

    def list_vc_ids(self) -> List[str]:
        """Return all VerificationCase IDs."""
        if not self.verification_dir.exists():
            return []
        return sorted(f.stem for f in self.verification_dir.glob("TC-*.md"))


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _cr_to_frontmatter(cr: ChangeRequest) -> dict:
    """Convert a ChangeRequest to a YAML-safe dict."""
    d: Dict = {
        "id": cr.id,
        "title": cr.title,
        "status": cr.status.value,
        "created": cr.created.isoformat() + "Z",
        "requester": cr.requester,
        "problem": cr.problem,
        "justification": cr.justification,
        "change_type": cr.change_type.value,
        "requirement_linkage_type": (
            cr.requirement_linkage_type.value if cr.requirement_linkage_type else None
        ),
        "impact_level": [il.value for il in cr.impact_level],
        "requirement_refs": cr.requirement_refs,
        "safety_impact": cr.safety_impact.value,
    }
    # Optional fields
    if cr.compliance_impact:
        d["compliance_impact"] = cr.compliance_impact
    if cr.reviewer:
        d["reviewer"] = cr.reviewer
    if cr.approval_date:
        d["approval_date"] = cr.approval_date.isoformat() + "Z"
    if cr.approval_comment:
        d["approval_comment"] = cr.approval_comment
    if cr.rejection_reason:
        d["rejection_reason"] = cr.rejection_reason
    if cr.affected_files:
        d["affected_files"] = cr.affected_files
    if cr.affected_verifications:
        d["affected_verifications"] = cr.affected_verifications
    if cr.commits:
        d["commits"] = cr.commits
    if cr.evidence_refs:
        d["evidence_refs"] = cr.evidence_refs
    if cr.is_emergency:
        d["is_emergency"] = True
        d["incident_id"] = cr.incident_id
        d["severity"] = cr.severity
        d["rollback_plan"] = cr.rollback_plan
        if cr.post_mortem_date:
            d["post_mortem_date"] = cr.post_mortem_date.isoformat() + "Z"
    if cr.root_cause_category:
        d["root_cause_category"] = cr.root_cause_category.value
    return d


def _frontmatter_to_cr(fm: dict, filepath: Path) -> ChangeRequest:
    """Construct a ChangeRequest from parsed frontmatter."""
    return ChangeRequest(
        id=fm["id"],
        title=fm["title"],
        status=CRStatus(fm["status"]),
        created=_parse_dt(fm["created"]),
        requester=fm["requester"],
        problem=fm.get("problem", ""),
        justification=fm.get("justification", ""),
        change_type=ChangeType(fm.get("change_type", "feature")),
        requirement_linkage_type=(
            RequirementLinkageType(fm["requirement_linkage_type"])
            if fm.get("requirement_linkage_type")
            else None
        ),
        impact_level=[ImpactLevel(il) for il in fm.get("impact_level", [])],
        requirement_refs=fm.get("requirement_refs", []),
        safety_impact=SafetyImpact(fm.get("safety_impact", "none")),
        compliance_impact=fm.get("compliance_impact"),
        reviewer=fm.get("reviewer"),
        approval_date=_parse_dt(fm["approval_date"]) if fm.get("approval_date") else None,
        approval_comment=fm.get("approval_comment"),
        rejection_reason=fm.get("rejection_reason"),
        affected_files=fm.get("affected_files", []),
        affected_verifications=fm.get("affected_verifications", []),
        commits=fm.get("commits", []),
        evidence_refs=fm.get("evidence_refs", []),
        is_emergency=fm.get("is_emergency", False),
        incident_id=fm.get("incident_id"),
        severity=fm.get("severity"),
        rollback_plan=fm.get("rollback_plan"),
        post_mortem_date=_parse_dt(fm["post_mortem_date"]) if fm.get("post_mortem_date") else None,
        root_cause_category=(
            RootCauseCategory(fm["root_cause_category"])
            if fm.get("root_cause_category")
            else None
        ),
        file_path=filepath,
    )


def _cr_to_body(cr: ChangeRequest) -> str:
    """Generate the Markdown body below the frontmatter."""
    sections = []
    sections.append(f"# {cr.id}: {cr.title}\n")
    sections.append("## Problem\n")
    sections.append(f"{cr.problem}\n")
    sections.append("## Justification\n")
    sections.append(f"{cr.justification}\n")
    if cr.affected_files:
        sections.append("## Affected Files\n")
        for f in cr.affected_files:
            sections.append(f"- `{f}`")
        sections.append("")
    if cr.affected_verifications:
        sections.append("## Verification Cases\n")
        for v in cr.affected_verifications:
            sections.append(f"- {v}")
        sections.append("")
    return "\n".join(sections)


def _vc_to_frontmatter(vc: VerificationCase) -> dict:
    d: Dict = {
        "id": vc.id,
        "title": vc.title,
        "type": vc.type.value,
        "status": vc.status.value,
        "description": vc.description,
        "validates": vc.validates,
        "implemented_in": vc.implemented_in,
        "component": vc.component,
        "owner": vc.owner,
        "created": vc.created.isoformat() + "Z",
    }
    if vc.prerequisite:
        d["prerequisite"] = vc.prerequisite
    if vc.test_data:
        d["test_data"] = vc.test_data
    if vc.last_run:
        d["last_run"] = vc.last_run.isoformat() + "Z"
    if vc.last_result:
        d["last_result"] = vc.last_result
    return d


def _frontmatter_to_vc(fm: dict, filepath: Path) -> VerificationCase:
    return VerificationCase(
        id=fm["id"],
        title=fm["title"],
        type=VerificationType(fm["type"]),
        status=VerificationStatus(fm["status"]),
        description=fm["description"],
        validates=fm["validates"],
        implemented_in=fm["implemented_in"],
        component=fm["component"],
        owner=fm["owner"],
        created=_parse_dt(fm["created"]),
        prerequisite=fm.get("prerequisite"),
        test_data=fm.get("test_data"),
        last_run=_parse_dt(fm["last_run"]) if fm.get("last_run") else None,
        last_result=fm.get("last_result"),
        file_path=filepath,
    )


# ---------------------------------------------------------------------------
# YAML frontmatter parser (lightweight — no third-party YAML parser needed
# beyond PyYAML which is already in the project)
# ---------------------------------------------------------------------------

def _parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter between --- delimiters."""
    if not content.startswith("---"):
        raise ValueError("No YAML frontmatter found")
    end = content.find("---", 3)
    if end == -1:
        raise ValueError("Unterminated YAML frontmatter")
    yaml_str = content[3:end].strip()
    return yaml.safe_load(yaml_str)


def _parse_dt(s: Optional[str]) -> datetime:
    """Parse ISO datetime string, tolerant of trailing Z."""
    if s is None:
        return datetime.now(timezone.utc)
    s = s.rstrip("Z")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.now(timezone.utc)
