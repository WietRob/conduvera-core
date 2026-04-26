"""
Compliance Change Control — Canonical Data Models.

Source: COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md §D.2
        COMPLIANCE_CHANGE_CONTROL_PROCESS.md §B
        COMPLIANCE_CHANGE_CONTROL_RULES.md §4, §9

Every enum value, every field, every cardinality constraint in this file
is measured against the frozen v2.0.0 documentation baseline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CRStatus(Enum):
    """9-state CR lifecycle — C-PROCESS §C.1."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"
    CLOSED = "closed"
    REJECTED = "rejected"
    EMERGENCY = "emergency"


class ChangeType(Enum):
    """CR classification — C-RULES §9.2."""

    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    TEST = "test"
    DOCS = "docs"


class ImpactLevel(Enum):
    """Impact classification — C-PROCESS §E."""

    SYS = "SYS"
    ARCH = "ARCH"
    SW = "SW"
    CODE = "CODE"


class SafetyImpact(Enum):
    """Safety impact rating — C-RULES §5."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RequirementLinkageType(Enum):
    """How a bugfix CR links to requirements — C-RULES §9.7."""

    EXISTING_REF = "existing_ref"
    UPDATED_REF = "updated_ref"
    NEW_REF = "new_ref"


class VerificationType(Enum):
    """VerificationCase type — C-PROCESS §B.3, C-RULES §1."""

    UNIT = "unit"
    SOFTWARE_INTEGRATION = "software_integration"
    SOFTWARE_VERIFICATION = "software_verification"
    SYSTEM_INTEGRATION = "system_integration"
    SYSTEM_VERIFICATION = "system_verification"


class VerificationStatus(Enum):
    """VerificationCase lifecycle — C-RULES §4.4."""

    DRAFT = "draft"
    APPROVED = "approved"
    PASSED = "passed"
    FAILED = "failed"
    DEPRECATED = "deprecated"


class RootCauseCategory(Enum):
    """Bugfix root-cause taxonomy — C-PROCESS §H.3."""

    IMPL_BUG = "impl_bug"
    REQ_AMBIGUOUS = "req_ambiguous"
    REQ_MISSING = "req_missing"
    ARCH_BUG = "arch_bug"
    SYS_BUG = "sys_bug"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ChangeRequest:
    """Canonical Change Request entity.

    Fields and cardinalities per C-RULES §5, C-PROCESS §C.4.
    """

    # ── Identity ──────────────────────────────────────────────────────────
    id: str                                    # CR-[0-9]{3,}
    title: str                                 # 10-80 chars at SUBMITTED
    status: CRStatus
    created: datetime
    requester: str

    # ── Content (required at SUBMITTED) ───────────────────────────────────
    problem: str = ""                          # min 50 chars at SUBMITTED
    justification: str = ""                    # min 20 chars at SUBMITTED

    # ── Classification (required at SUBMITTED) ───────────────────────────
    change_type: ChangeType = ChangeType.FEATURE
    requirement_linkage_type: Optional[RequirementLinkageType] = None

    # ── Impact (required at SUBMITTED) ───────────────────────────────────
    impact_level: List[ImpactLevel] = field(default_factory=list)
    requirement_refs: List[str] = field(default_factory=list)      # min 1 at SUBMITTED
    safety_impact: SafetyImpact = SafetyImpact.NONE
    compliance_impact: Optional[List[str]] = None

    # ── Lifecycle (required at APPROVED+) ────────────────────────────────
    reviewer: Optional[str] = None
    approval_date: Optional[datetime] = None
    approval_comment: Optional[str] = None
    rejection_reason: Optional[str] = None

    # ── Implementation (required at IMPLEMENTED+) ───────────────────────
    affected_files: List[str] = field(default_factory=list)
    affected_verifications: List[str] = field(default_factory=list)
    commits: List[str] = field(default_factory=list)

    # ── Evidence (required at VERIFIED+) ─────────────────────────────────
    evidence_refs: List[str] = field(default_factory=list)

    # ── Emergency (EMERGENCY state) ──────────────────────────────────────
    is_emergency: bool = False
    incident_id: Optional[str] = None
    severity: Optional[str] = None
    rollback_plan: Optional[str] = None
    post_mortem_date: Optional[datetime] = None

    # ── Bugfix metadata ─────────────────────────────────────────────────
    root_cause_category: Optional[RootCauseCategory] = None

    # ── Storage ──────────────────────────────────────────────────────────
    file_path: Optional[Path] = None


@dataclass
class VerificationCase:
    """Planned verification artifact (specification).

    Fields per C-RULES §4.4, C-PROCESS §B.3.
    """

    id: str                                    # TC-{TYPE}-{Nr}
    title: str
    type: VerificationType
    status: VerificationStatus
    description: str
    validates: List[str]                       # min 1 requirement ID
    implemented_in: str                        # test file path
    component: str
    owner: str
    created: datetime

    # ── Optional ─────────────────────────────────────────────────────────
    prerequisite: Optional[str] = None
    test_data: Optional[str] = None
    last_run: Optional[datetime] = None
    last_result: Optional[str] = None          # PASS, FAIL, SKIP

    # ── Storage ──────────────────────────────────────────────────────────
    file_path: Optional[Path] = None


@dataclass
class VerificationResult:
    """Execution result for a single VerificationCase — C-PROCESS §B.4."""

    verification_case_id: str                  # TC-{TYPE}-{Nr}
    result: str                                # PASS, FAIL, SKIP
    executed_at: datetime
    output: str = ""
    validates: List[str] = field(default_factory=list)
