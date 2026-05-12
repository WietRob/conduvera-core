"""
Compliance Change Control — Service Layer.

Source: COMPLIANCE_CHANGE_CONTROL_RULES.md §7 (Interface to B)
       COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md §G

Exposed services:
  - ChangeRequestService  —  CRUD + state transitions + validation
  - VerificationService   —  VerificationCase CRUD + type validation
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .models import (
    ChangeRequest,
    ChangeType,
    CRStatus,
    ImpactLevel,
    RequirementLinkageType,
    RootCauseCategory,
    SafetyImpact,
    VerificationCase,
    VerificationResult,
    VerificationStatus,
    VerificationType,
)
from .state_machine import CRStateMachine, InvalidTransitionError, MissingFieldsError
from .validation import CRValidator
from .evidence import CREvidenceGenerator
from .persistence import CRPersistence, VCPersistence


class ChangeRequestService:
    """High-level service for ChangeRequest lifecycle.

    Per C-RULES §7, this is the primary interface consumed by
    the Accountable Agent Layer (B).
    """

    def __init__(
        self,
        changes_dir: Optional[Path] = None,
        evidence_dir: Optional[Path] = None,
    ):
        self.persistence = CRPersistence(changes_dir)
        self.evidence_gen = CREvidenceGenerator(evidence_dir)
        self.state_machine = CRStateMachine()
        self.validator = CRValidator()

    # ── Create ───────────────────────────────────────────────────────────

    def create_cr(
        self,
        title: str,
        requester: str,
        problem: str = "",
        justification: str = "",
        change_type: str = "feature",
        requirement_linkage_type: Optional[str] = None,
        impact_level: Optional[List[str]] = None,
        requirement_refs: Optional[List[str]] = None,
        safety_impact: str = "none",
        compliance_impact: Optional[List[str]] = None,
        is_emergency: bool = False,
        incident_id: Optional[str] = None,
        severity: Optional[str] = None,
        rollback_plan: Optional[str] = None,
    ) -> ChangeRequest:
        """Create a new CR in DRAFT (or EMERGENCY) state."""
        cr_id = f"CR-{self.persistence.next_cr_number():03d}"
        status = CRStatus.EMERGENCY if is_emergency else CRStatus.DRAFT

        cr = ChangeRequest(
            id=cr_id,
            title=title,
            status=status,
            created=datetime.now(timezone.utc),
            requester=requester,
            problem=problem,
            justification=justification,
            change_type=ChangeType(change_type),
            requirement_linkage_type=(
                RequirementLinkageType(requirement_linkage_type)
                if requirement_linkage_type
                else None
            ),
            impact_level=[ImpactLevel(il) for il in (impact_level or [])],
            requirement_refs=requirement_refs or [],
            safety_impact=SafetyImpact(safety_impact),
            compliance_impact=compliance_impact,
            is_emergency=is_emergency,
            incident_id=incident_id,
            severity=severity,
            rollback_plan=rollback_plan,
        )

        self.persistence.save(cr)
        return cr

    # ── Read ─────────────────────────────────────────────────────────────

    def get_cr(self, cr_id: str) -> ChangeRequest:
        """Load a CR from disk."""
        return self.persistence.load(cr_id)

    def list_crs(self, status: Optional[str] = None) -> List[ChangeRequest]:
        """List all CRs, optionally filtered by status."""
        cr_ids = self.persistence.list_cr_ids()
        crs = []
        for cid in cr_ids:
            try:
                cr = self.persistence.load(cid)
                if status is None or cr.status.value == status:
                    crs.append(cr)
            except Exception:
                continue
        return crs

    # ── State Transitions ────────────────────────────────────────────────

    def transition_cr(
        self,
        cr_id: str,
        to_status: str,
        actor: str = "",
        context: Optional[dict] = None,
    ) -> ChangeRequest:
        """Transition a CR to a new state.

        Returns the updated CR (persisted).
        Raises InvalidTransitionError or MissingFieldsError on failure.
        """
        cr = self.persistence.load(cr_id)
        target = CRStatus(to_status)

        # Run validations
        issues = self.validator.validate_for_transition(cr, target)
        blocking = [i for i in issues if i["severity"] == "BLOCKING"]
        if blocking:
            msgs = "; ".join(i["message"] for i in blocking)
            raise ValueError(f"Validation blocking: {msgs}")

        # Execute transition (checks matrix + mandatory fields)
        self.state_machine.transition(cr, target, actor, context or {})

        # Auto-set fields based on transition
        self._apply_transition_side_effects(cr, target, actor, context)

        self.persistence.save(cr)
        return cr

    def submit_cr(self, cr_id: str, actor: str = "") -> ChangeRequest:
        """Shortcut: DRAFT → SUBMITTED."""
        return self.transition_cr(cr_id, "submitted", actor)

    def approve_cr(self, cr_id: str, reviewer: str, comment: str = "") -> ChangeRequest:
        """Shortcut: SUBMITTED → APPROVED."""
        cr = self.persistence.load(cr_id)
        cr.reviewer = reviewer
        cr.approval_date = datetime.now(timezone.utc)
        if comment:
            cr.approval_comment = comment
        self.persistence.save(cr)
        return self.transition_cr(cr_id, "approved", reviewer)

    def reject_cr(self, cr_id: str, reason: str, actor: str = "") -> ChangeRequest:
        """Reject a CR (sets rejection_reason, transitions to REJECTED)."""
        cr = self.persistence.load(cr_id)
        cr.rejection_reason = reason
        self.persistence.save(cr)
        return self.transition_cr(cr_id, "rejected", actor)

    def start_cr(self, cr_id: str) -> ChangeRequest:
        """Shortcut: APPROVED → IN_PROGRESS."""
        return self.transition_cr(cr_id, "in_progress")

    def complete_cr(
        self,
        cr_id: str,
        affected_files: Optional[List[str]] = None,
        affected_verifications: Optional[List[str]] = None,
        commits: Optional[List[str]] = None,
    ) -> ChangeRequest:
        """Shortcut: IN_PROGRESS → IMPLEMENTED."""
        cr = self.persistence.load(cr_id)
        if affected_files:
            cr.affected_files = affected_files
        if affected_verifications:
            cr.affected_verifications = affected_verifications
        if commits:
            cr.commits = commits
        self.persistence.save(cr)
        return self.transition_cr(cr_id, "implemented")

    def verify_cr(self, cr_id: str) -> ChangeRequest:
        """Shortcut: IMPLEMENTED → VERIFIED."""
        return self.transition_cr(cr_id, "verified")

    def close_cr(self, cr_id: str) -> ChangeRequest:
        """Shortcut: VERIFIED → CLOSED."""
        return self.transition_cr(cr_id, "closed")

    def revise_cr(self, cr_id: str) -> ChangeRequest:
        """Shortcut: REJECTED → DRAFT."""
        return self.transition_cr(cr_id, "draft")

    # ── Validation ───────────────────────────────────────────────────────

    def validate_cr(self, cr_id: str) -> List[dict]:
        """Run all validations on a CR and return issues."""
        cr = self.persistence.load(cr_id)
        return self.validator.validate_all(cr)

    def validate_links(self, cr_id: str) -> bool:
        """Return True if all validations pass (no BLOCKING issues)."""
        issues = self.validate_cr(cr_id)
        return not any(i["severity"] == "BLOCKING" for i in issues)

    def validate_id_format(self, ref_id: str) -> bool:
        """Validate an arbitrary ID format."""
        valid, _ = self.validator.validate_id_format(ref_id)
        return valid

    def check_status(self, cr_id: str) -> CRStatus:
        """Return the current CR status."""
        cr = self.persistence.load(cr_id)
        return cr.status

    # ── Evidence ─────────────────────────────────────────────────────────

    def generate_evidence(
        self,
        cr_id: str,
        verification_results: Optional[List[VerificationResult]] = None,
    ) -> Path:
        """Generate evidence for a CR."""
        cr = self.persistence.load(cr_id)
        path = self.evidence_gen.generate(cr, verification_results)
        # Attach evidence ref to CR
        cr.evidence_refs.append(str(path))
        self.persistence.save(cr)
        return path

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _apply_transition_side_effects(
        cr: ChangeRequest,
        target: CRStatus,
        actor: str,
        context: Optional[dict],
    ) -> None:
        """Set auto-derived fields on transition."""
        # Nothing extra needed — approval/rejection fields are set
        # by the shortcut methods before calling transition_cr.


class VerificationService:
    """High-level service for VerificationCase management.

    Per C-RULES §7, exposed to the Accountable Agent Layer.
    """

    def __init__(self, verification_dir: Optional[Path] = None):
        self.persistence = VCPersistence(verification_dir)
        self.validator = CRValidator()

    def create_verification(
        self,
        title: str,
        type_str: str,
        validates: List[str],
        implemented_in: str,
        component: str,
        owner: str,
        description: str = "",
    ) -> VerificationCase:
        """Create a new VerificationCase in DRAFT state."""
        vc_type = VerificationType(type_str)
        vc_id = self._next_vc_id(vc_type)

        vc = VerificationCase(
            id=vc_id,
            title=title,
            type=vc_type,
            status=VerificationStatus.DRAFT,
            description=description,
            validates=validates,
            implemented_in=implemented_in,
            component=component,
            owner=owner,
            created=datetime.now(timezone.utc),
        )

        self.persistence.save(vc)
        return vc

    def get_verification(self, tc_id: str) -> VerificationCase:
        """Load a VerificationCase from disk."""
        return self.persistence.load(tc_id)

    def list_verifications(self, validates: Optional[str] = None) -> List[VerificationCase]:
        """List all VerificationCases, optionally filtered by validates."""
        vc_ids = self.persistence.list_vc_ids()
        vcs = []
        for vid in vc_ids:
            try:
                vc = self.persistence.load(vid)
                if validates is None or validates in vc.validates:
                    vcs.append(vc)
            except Exception:
                continue
        return vcs

    def validate_verification_type(self, tc_id: str, req_id: str) -> bool:
        """Check that a VerificationCase type matches the requirement level."""
        vc = self.persistence.load(tc_id)
        valid, _ = self.validator.validate_verification_type_mapping(vc.type, req_id)
        return valid

    def _next_vc_id(self, vc_type: VerificationType) -> str:
        """Generate the next VC ID for a given type."""
        prefix_map = {
            VerificationType.UNIT: "TC-UT-",
            VerificationType.SOFTWARE_INTEGRATION: "TC-SIT-",
            VerificationType.SOFTWARE_VERIFICATION: "TC-SVT-",
            VerificationType.SYSTEM_INTEGRATION: "TC-SYSIT-",
            VerificationType.SYSTEM_VERIFICATION: "TC-SYST-",
        }
        prefix = prefix_map[vc_type]
        existing = self.persistence.list_vc_ids()
        nums = []
        for eid in existing:
            if eid.startswith(prefix):
                try:
                    nums.append(int(eid[len(prefix):]))
                except ValueError:
                    continue
        next_num = max(nums, default=0) + 1
        return f"{prefix}{next_num:03d}"
