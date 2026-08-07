"""
Compliance Change Control — 9-State CR State Machine.

Source: COMPLIANCE_CHANGE_CONTROL_PROCESS.md §C.1–C.4
Transition matrix:  C-PROCESS §C.2
Mandatory fields:   C-PROCESS §C.4
"""

from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional, Set

from .models import CRStatus, ChangeRequest


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class InvalidTransitionError(Exception):
    """Raised when a state transition is not in the valid matrix."""


class MissingFieldsError(Exception):
    """Raised when mandatory fields for the target state are absent."""


# ---------------------------------------------------------------------------
# Mandatory-field table  —  C-PROCESS §C.4
#
# ✓ = required, ○ = optional (omitted from dict), - = not applicable
# ---------------------------------------------------------------------------

_MANDATORY_FIELDS: Dict[CRStatus, Set[str]] = {
    CRStatus.DRAFT: {
        "id", "title", "status", "created", "requester",
    },
    CRStatus.SUBMITTED: {
        "id", "title", "status", "created", "requester",
        "problem", "justification", "change_type",
        "impact_level", "requirement_refs", "safety_impact",
    },
    CRStatus.APPROVED: {
        "id", "title", "status", "created", "requester",
        "problem", "justification", "change_type",
        "impact_level", "requirement_refs", "safety_impact",
        "reviewer", "approval_date",
    },
    CRStatus.IN_PROGRESS: {
        "id", "title", "status", "created", "requester",
        "problem", "justification", "change_type",
        "impact_level", "requirement_refs", "safety_impact",
        "reviewer", "approval_date",
    },
    CRStatus.IMPLEMENTED: {
        "id", "title", "status", "created", "requester",
        "problem", "justification", "change_type",
        "impact_level", "requirement_refs", "safety_impact",
        "reviewer", "approval_date",
        "affected_files", "affected_verifications", "commits",
    },
    CRStatus.VERIFIED: {
        "id", "title", "status", "created", "requester",
        "problem", "justification", "change_type",
        "impact_level", "requirement_refs", "safety_impact",
        "reviewer", "approval_date",
        "affected_files", "affected_verifications", "commits",
        "evidence_refs",
    },
    CRStatus.CLOSED: {
        "id", "title", "status", "created", "requester",
        "problem", "justification", "change_type",
        "impact_level", "requirement_refs", "safety_impact",
        "reviewer", "approval_date",
        "affected_files", "affected_verifications", "commits",
        "evidence_refs",
    },
    CRStatus.REJECTED: {
        "id", "title", "status", "created", "requester",
        "rejection_reason",
    },
    CRStatus.EMERGENCY: {
        "id", "title", "status", "created", "requester",
        "is_emergency", "incident_id",
    },
}

# Fields that are conditionally required when change_type == BUGFIX
# at SUBMITTED and beyond — C-RULES §9.7, C-PROCESS §C.4 footnote *
_BUGFIX_REQUIRED_FIELDS: Set[str] = {"requirement_linkage_type"}


# ---------------------------------------------------------------------------
# Transition matrix  —  C-PROCESS §C.2
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: Dict[CRStatus, FrozenSet[CRStatus]] = {
    CRStatus.DRAFT: frozenset({CRStatus.SUBMITTED, CRStatus.REJECTED}),
    CRStatus.SUBMITTED: frozenset({CRStatus.APPROVED, CRStatus.REJECTED, CRStatus.DRAFT}),
    CRStatus.APPROVED: frozenset({CRStatus.IN_PROGRESS, CRStatus.REJECTED}),
    CRStatus.IN_PROGRESS: frozenset({CRStatus.IMPLEMENTED, CRStatus.REJECTED}),
    CRStatus.IMPLEMENTED: frozenset({CRStatus.VERIFIED, CRStatus.REJECTED}),
    CRStatus.VERIFIED: frozenset({CRStatus.CLOSED}),
    CRStatus.CLOSED: frozenset(),
    CRStatus.REJECTED: frozenset({CRStatus.DRAFT}),
    CRStatus.EMERGENCY: frozenset({CRStatus.SUBMITTED}),
}


# ---------------------------------------------------------------------------
# State Machine
# ---------------------------------------------------------------------------


class CRStateMachine:
    """Implements exact transition matrix from C-PROCESS §C.2."""

    # Expose for external consumers (e.g. validation, CLI help)
    VALID_TRANSITIONS = _VALID_TRANSITIONS
    MANDATORY_FIELDS = _MANDATORY_FIELDS
    BUGFIX_REQUIRED_FIELDS = _BUGFIX_REQUIRED_FIELDS

    # ── Query ────────────────────────────────────────────────────────────

    def can_transition(self, cr: ChangeRequest, to_status: CRStatus) -> bool:
        """Return True if the raw transition is allowed by the matrix."""
        return to_status in _VALID_TRANSITIONS.get(cr.status, frozenset())

    def missing_fields(self, cr: ChangeRequest, target: CRStatus) -> List[str]:
        """Return names of mandatory fields that are empty/missing for *target*."""
        required = _MANDATORY_FIELDS.get(target, set())
        missing: List[str] = []
        for f in sorted(required):
            val = getattr(cr, f, None)
            if _is_empty(val):
                missing.append(f)

        # Conditional: bugfix requires linkage_type from SUBMITTED onward
        if target not in (CRStatus.DRAFT, CRStatus.EMERGENCY):
            from .models import ChangeType
            try:
                is_bugfix = cr.change_type == ChangeType.BUGFIX
            except Exception:
                is_bugfix = False
            if is_bugfix:
                if _is_empty(cr.requirement_linkage_type):
                    missing.append("requirement_linkage_type")

        return missing

    # ── Execute ──────────────────────────────────────────────────────────

    def transition(
        self,
        cr: ChangeRequest,
        to_status: CRStatus,
        actor: str = "",
        context: Optional[dict] = None,
    ) -> ChangeRequest:
        """Validate + execute a state transition.

        Raises:
            InvalidTransitionError: transition not in matrix
            MissingFieldsError: mandatory fields absent for target state
        """
        if not self.can_transition(cr, to_status):
            raise InvalidTransitionError(
                f"Cannot transition {cr.status.value} → {to_status.value}"
            )

        missing = self.missing_fields(cr, to_status)
        if missing:
            raise MissingFieldsError(
                f"Missing mandatory fields for {to_status.value}: {', '.join(missing)}"
            )

        cr.status = to_status
        return cr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_empty(val) -> bool:
    """Return True if a field value is considered unset."""
    if val is None:
        return True
    if isinstance(val, (list, str, set)) and len(val) == 0:
        return True
    if isinstance(val, bool):
        return False  # False is a valid value, not "empty"
    return False
