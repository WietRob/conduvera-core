"""
Contract Test 1: CR creation with mandatory fields.
Contract Test 2: Invalid transition blocked.
Contract Test 3: Bugfix without SW-REQ blocked.
Contract Test 4: Bugfix existing_ref passes.
Contract Test 5: Bugfix new_ref without approved SW-REQ blocked.
Contract Test 6: Emergency CR rule enforced.
Contract Test 7: VerificationCase linkage enforced before close.
Contract Test 8: Evidence schema version and required fields verified.

Source: Task spec REQUIRED TEST COVERAGE items 1-8
"""

from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path

from curaops.skills.change_request import (
    ChangeRequest,
    ChangeType,
    CRStatus,
    CRStateMachine,
    CRValidator,
    CREvidenceGenerator,
    ChangeRequestService,
    ImpactLevel,
    InvalidTransitionError,
    MissingFieldsError,
    RequirementLinkageType,
    RootCauseCategory,
    SafetyImpact,
    VerificationCase,
    VerificationResult,
    VerificationService,
    VerificationStatus,
    VerificationType,
    VCPersistence,
)


# ═══════════════════════════════════════════════════════════════════════
# Contract 1: CR creation with mandatory fields
# ═══════════════════════════════════════════════════════════════════════

class TestContract1CRCreation:
    """CR creation with mandatory fields per C-PROCESS §C.4."""

    def test_draft_requires_identity_fields(self):
        """DRAFT state requires: id, title, status, created, requester."""
        cr = ChangeRequest(
            id="CR-001",
            title="Test CR",
            status=CRStatus.DRAFT,
            created=datetime.now(timezone.utc),
            requester="dev@example.com",
        )
        assert cr.id == "CR-001"
        assert cr.status == CRStatus.DRAFT
        assert cr.change_type == ChangeType.FEATURE  # default

    def test_draft_missing_title_fails_submission(self):
        """Cannot transition DRAFT→SUBMITTED without title."""
        sm = CRStateMachine()
        cr = ChangeRequest(
            id="CR-001",
            title="",  # empty
            status=CRStatus.DRAFT,
            created=datetime.now(timezone.utc),
            requester="dev@example.com",
        )
        missing = sm.missing_fields(cr, CRStatus.SUBMITTED)
        assert "title" in missing

    def test_submitted_requires_content_fields(self):
        """SUBMITTED requires problem, justification, change_type, impact, refs, safety."""
        sm = CRStateMachine()
        cr = ChangeRequest(
            id="CR-001",
            title="A test change request title",
            status=CRStatus.DRAFT,
            created=datetime.now(timezone.utc),
            requester="dev@example.com",
            problem="A" * 50,
            justification="B" * 20,
            change_type=ChangeType.FEATURE,
            impact_level=[ImpactLevel.SW],
            requirement_refs=["SW-REQ-001"],
            safety_impact=SafetyImpact.NONE,
        )
        missing = sm.missing_fields(cr, CRStatus.SUBMITTED)
        assert len(missing) == 0, f"Unexpected missing: {missing}"

    def test_full_cr_creation_via_service(self, tmp_path):
        """End-to-end CR creation via ChangeRequestService."""
        svc = ChangeRequestService(
            changes_dir=tmp_path / "changes",
            evidence_dir=tmp_path / "evidence",
        )
        cr = svc.create_cr(
            title="Fix authentication vulnerability",
            requester="dev@example.com",
            problem="OAuth2 token replay vulnerability in auth module",
            justification="Security compliance requirement",
            change_type="bugfix",
            requirement_linkage_type="existing_ref",
            impact_level=["SW"],
            requirement_refs=["SW-REQ-003"],
            safety_impact="high",
        )
        assert cr.id.startswith("CR-")
        assert cr.status == CRStatus.DRAFT
        assert cr.change_type == ChangeType.BUGFIX
        # Verify persisted
        loaded = svc.get_cr(cr.id)
        assert loaded.title == "Fix authentication vulnerability"


# ═══════════════════════════════════════════════════════════════════════
# Contract 2: Invalid transition blocked
# ═══════════════════════════════════════════════════════════════════════

class TestContract2InvalidTransition:
    """Invalid transitions are blocked per C-PROCESS §C.2 matrix."""

    def test_draft_to_closed_blocked(self):
        sm = CRStateMachine()
        cr = ChangeRequest(
            id="CR-001", title="T", status=CRStatus.DRAFT,
            created=datetime.now(timezone.utc), requester="dev",
        )
        assert not sm.can_transition(cr, CRStatus.CLOSED)
        with pytest.raises(InvalidTransitionError):
            sm.transition(cr, CRStatus.CLOSED)

    def test_submitted_to_closed_blocked(self):
        sm = CRStateMachine()
        cr = ChangeRequest(
            id="CR-001", title="T", status=CRStatus.SUBMITTED,
            created=datetime.now(timezone.utc), requester="dev",
        )
        with pytest.raises(InvalidTransitionError):
            sm.transition(cr, CRStatus.CLOSED)

    def test_closed_is_terminal(self):
        sm = CRStateMachine()
        cr = ChangeRequest(
            id="CR-001", title="T", status=CRStatus.CLOSED,
            created=datetime.now(timezone.utc), requester="dev",
        )
        # CLOSED cannot go anywhere
        for target in CRStatus:
            if target == CRStatus.CLOSED:
                continue
            assert not sm.can_transition(cr, target), f"CLOSED → {target} should be blocked"

    def test_valid_forward_chain(self):
        """DRAFT→SUBMITTED→APPROVED→IN_PROGRESS→IMPLEMENTED→VERIFIED→CLOSED works."""
        sm = CRStateMachine()
        cr = _make_full_cr(status=CRStatus.DRAFT)
        chain = [CRStatus.SUBMITTED, CRStatus.APPROVED, CRStatus.IN_PROGRESS,
                 CRStatus.IMPLEMENTED, CRStatus.VERIFIED, CRStatus.CLOSED]
        for target in chain:
            sm.transition(cr, target, actor="test")
        assert cr.status == CRStatus.CLOSED


# ═══════════════════════════════════════════════════════════════════════
# Contract 3: Bugfix without SW-REQ blocked
# ═══════════════════════════════════════════════════════════════════════

class TestContract3BugfixNoSWREQ:
    """Bugfix without SW-REQ linkage is BLOCKING per C-RULES §9.1."""

    def test_bugfix_no_sw_req_blocked(self):
        v = CRValidator()
        cr = ChangeRequest(
            id="CR-001", title="Bug fix", status=CRStatus.SUBMITTED,
            created=datetime.now(timezone.utc), requester="dev",
            problem="X" * 50, justification="Y" * 20,
            change_type=ChangeType.BUGFIX,
            requirement_linkage_type=RequirementLinkageType.EXISTING_REF,
            impact_level=[ImpactLevel.SW],
            requirement_refs=["SYS-REQ-001"],  # SYS-REQ but no SW-REQ!
            safety_impact=SafetyImpact.NONE,
        )
        issues = v.validate_bugfix_rules(cr)
        blocking = [i for i in issues if i["severity"] == "BLOCKING"]
        assert any("SW-REQ" in i["message"] for i in blocking)

    def test_bugfix_no_linkage_type_blocked(self):
        v = CRValidator()
        cr = ChangeRequest(
            id="CR-001", title="Bug fix", status=CRStatus.SUBMITTED,
            created=datetime.now(timezone.utc), requester="dev",
            problem="X" * 50, justification="Y" * 20,
            change_type=ChangeType.BUGFIX,
            impact_level=[ImpactLevel.SW],
            requirement_refs=["SW-REQ-001"],
            safety_impact=SafetyImpact.NONE,
            # requirement_linkage_type is None!
        )
        issues = v.validate_bugfix_rules(cr)
        blocking = [i for i in issues if i["severity"] == "BLOCKING"]
        assert any("requirement_linkage_type" in i["message"] for i in blocking)


# ═══════════════════════════════════════════════════════════════════════
# Contract 4: Bugfix existing_ref passes
# ═══════════════════════════════════════════════════════════════════════

class TestContract4BugfixExistingRef:
    """Bugfix with existing_ref to SW-REQ passes validation — C-RULES §9.3."""

    def test_bugfix_existing_ref_valid(self):
        v = CRValidator()
        cr = ChangeRequest(
            id="CR-001", title="Bug fix", status=CRStatus.SUBMITTED,
            created=datetime.now(timezone.utc), requester="dev",
            problem="X" * 50, justification="Y" * 20,
            change_type=ChangeType.BUGFIX,
            requirement_linkage_type=RequirementLinkageType.EXISTING_REF,
            impact_level=[ImpactLevel.SW],
            requirement_refs=["SW-REQ-003"],
            safety_impact=SafetyImpact.NONE,
        )
        issues = v.validate_bugfix_rules(cr)
        blocking = [i for i in issues if i["severity"] == "BLOCKING"]
        assert len(blocking) == 0, f"Unexpected blocking: {blocking}"

    def test_full_bugfix_lifecycle(self, tmp_path):
        """Bugfix CR with existing_ref through full lifecycle."""
        svc = ChangeRequestService(
            changes_dir=tmp_path / "changes",
            evidence_dir=tmp_path / "evidence",
        )
        cr = svc.create_cr(
            title="Fix null pointer in auth",
            requester="dev@example.com",
            problem="Null pointer dereference when token is missing",
            justification="Causes 500 errors in production",
            change_type="bugfix",
            requirement_linkage_type="existing_ref",
            impact_level=["SW"],
            requirement_refs=["SW-REQ-003"],
            safety_impact="none",
        )
        svc.submit_cr(cr.id)
        svc.approve_cr(cr.id, reviewer="lead@example.com")
        svc.start_cr(cr.id)
        svc.complete_cr(
            cr.id,
            affected_files=["src/auth.py"],
            affected_verifications=["TC-SVT-012"],
            commits=["abc123"],
        )
        # Evidence must be generated before verify (VERIFIED requires evidence_refs)
        svc.generate_evidence(cr.id)
        svc.verify_cr(cr.id)
        svc.close_cr(cr.id)
        assert svc.check_status(cr.id) == CRStatus.CLOSED


# ═══════════════════════════════════════════════════════════════════════
# Contract 5: Bugfix new_ref without approved SW-REQ blocked
# ═══════════════════════════════════════════════════════════════════════

class TestContract5BugfixNewRef:
    """Bugfix with new_ref but no SW-REQ linked is BLOCKING — C-RULES §9.3."""

    def test_bugfix_new_ref_no_sw_req_blocked(self):
        v = CRValidator()
        cr = ChangeRequest(
            id="CR-001", title="Bug fix", status=CRStatus.SUBMITTED,
            created=datetime.now(timezone.utc), requester="dev",
            problem="X" * 50, justification="Y" * 20,
            change_type=ChangeType.BUGFIX,
            requirement_linkage_type=RequirementLinkageType.NEW_REF,
            impact_level=[ImpactLevel.SW],
            requirement_refs=["SYS-REQ-001"],  # no SW-REQ!
            safety_impact=SafetyImpact.NONE,
        )
        issues = v.validate_bugfix_rules(cr)
        blocking = [i for i in issues if i["severity"] == "BLOCKING"]
        assert any("new_ref" in i["message"].lower() or "SW-REQ" in i["message"] for i in blocking)


# ═══════════════════════════════════════════════════════════════════════
# Contract 6: Emergency CR rule enforced
# ═══════════════════════════════════════════════════════════════════════

class TestContract6Emergency:
    """Emergency CR rules enforced per C-PROCESS §I, C-RULES §9.5."""

    def test_emergency_requires_incident_id(self):
        """Emergency CR must have incident_id — C-PROCESS §I.2."""
        v = CRValidator()
        cr = ChangeRequest(
            id="CR-001", title="Hotfix", status=CRStatus.EMERGENCY,
            created=datetime.now(timezone.utc), requester="dev",
            is_emergency=True,
            # incident_id is None!
        )
        issues = v.validate_emergency_rules(cr)
        blocking = [i for i in issues if i["severity"] == "BLOCKING"]
        assert any("incident_id" in i["message"] for i in blocking)

    def test_emergency_requires_post_mortem_date(self):
        """Emergency CR must commit post_mortem_date before E→S — C-PROCESS §I.2."""
        v = CRValidator()
        cr = ChangeRequest(
            id="CR-001", title="Hotfix", status=CRStatus.EMERGENCY,
            created=datetime.now(timezone.utc), requester="dev",
            is_emergency=True,
            incident_id="INC-2026-001",
            # post_mortem_date is None!
        )
        issues = v.validate_emergency_rules(cr)
        blocking = [i for i in issues if i["severity"] == "BLOCKING"]
        assert any("post_mortem_date" in i["message"] for i in blocking)

    def test_emergency_can_transition_to_submitted(self):
        """E→S is valid per C-PROCESS §C.2."""
        sm = CRStateMachine()
        cr = ChangeRequest(
            id="CR-001", title="Hotfix", status=CRStatus.EMERGENCY,
            created=datetime.now(timezone.utc), requester="dev",
            is_emergency=True,
            incident_id="INC-2026-001",
            post_mortem_date=datetime(2026, 5, 1),
        )
        assert sm.can_transition(cr, CRStatus.SUBMITTED)

    def test_emergency_creation_via_service(self, tmp_path):
        """Create emergency CR via service."""
        svc = ChangeRequestService(
            changes_dir=tmp_path / "changes",
            evidence_dir=tmp_path / "evidence",
        )
        cr = svc.create_cr(
            title="Hotfix: data leak",
            requester="oncall@example.com",
            problem="Sensitive data appearing in application logs",
            justification="Immediate production fix required",
            change_type="bugfix",
            requirement_linkage_type="existing_ref",
            impact_level=["SW"],
            requirement_refs=["SW-REQ-005"],
            safety_impact="high",
            is_emergency=True,
            incident_id="INC-2026-001",
            severity="P0",
        )
        assert cr.status == CRStatus.EMERGENCY
        assert cr.is_emergency is True
        assert cr.incident_id == "INC-2026-001"


# ═══════════════════════════════════════════════════════════════════════
# Contract 7: VerificationCase linkage enforced before close
# ═══════════════════════════════════════════════════════════════════════

class TestContract7VerificationLinkage:
    """VerificationCase must be linked before CR can close — C-RULES §5."""

    def test_bugfix_at_implemented_without_verifications_blocked(self):
        """Bugfix at IMPLEMENTED with empty affected_verifications is BLOCKING."""
        v = CRValidator()
        cr = ChangeRequest(
            id="CR-001", title="Bug fix", status=CRStatus.IMPLEMENTED,
            created=datetime.now(timezone.utc), requester="dev",
            problem="X" * 50, justification="Y" * 20,
            change_type=ChangeType.BUGFIX,
            requirement_linkage_type=RequirementLinkageType.EXISTING_REF,
            impact_level=[ImpactLevel.SW],
            requirement_refs=["SW-REQ-001"],
            safety_impact=SafetyImpact.NONE,
            affected_files=["src/auth.py"],
            commits=["abc123"],
            affected_verifications=[],  # EMPTY!
        )
        issues = v.validate_bugfix_rules(cr)
        blocking = [i for i in issues if i["severity"] == "BLOCKING"]
        assert any("VerificationCase" in i["message"] for i in blocking)

    def test_verification_type_mapping_sw_req(self):
        """SW-REQ must be verified by software_verification (TC-SVT-*) — C-PROCESS §D.4."""
        v = CRValidator()
        ok, msg = v.validate_verification_type_mapping(
            VerificationType.SOFTWARE_VERIFICATION, "SW-REQ-001"
        )
        assert ok

        bad, msg = v.validate_verification_type_mapping(
            VerificationType.UNIT, "SW-REQ-001"
        )
        assert not bad

    def test_verification_type_mapping_sys_req(self):
        """SYS-REQ must be verified by system_verification (TC-SYST-*) — C-PROCESS §D.4."""
        v = CRValidator()
        ok, _ = v.validate_verification_type_mapping(
            VerificationType.SYSTEM_VERIFICATION, "SYS-REQ-001"
        )
        assert ok

        bad, _ = v.validate_verification_type_mapping(
            VerificationType.SOFTWARE_VERIFICATION, "SYS-REQ-001"
        )
        assert not bad

    def test_verification_case_creation(self, tmp_path):
        """Create a VerificationCase via VerificationService."""
        vs = VerificationService(verification_dir=tmp_path / "verification")
        vc = vs.create_verification(
            title="Verify null token handling",
            type_str="software_verification",
            validates=["SW-REQ-001"],
            implemented_in="tests/test_auth.py",
            component="auth",
            owner="qa@example.com",
            description="Test that null tokens are rejected",
        )
        assert vc.id.startswith("TC-SVT-")
        assert vc.status == VerificationStatus.DRAFT
        assert "SW-REQ-001" in vc.validates

        loaded = vs.get_verification(vc.id)
        assert loaded.title == "Verify null token handling"


# ═══════════════════════════════════════════════════════════════════════
# Contract 8: Evidence schema version and required fields verified
# ═══════════════════════════════════════════════════════════════════════

class TestContract8EvidenceSchema:
    """Evidence must comply with CCC-1.1.0 schema — C-PROCESS §H.2."""

    def test_evidence_schema_version(self):
        """Evidence must have schema_version = CCC-1.1.0."""
        cr = _make_full_cr(status=CRStatus.IMPLEMENTED)
        gen = CREvidenceGenerator()
        evidence = gen.generate_to_dict(cr)
        assert evidence["schema_version"] == "CCC-1.1.0"

    def test_evidence_required_fields(self):
        """Evidence must contain: cr_id, timestamp, status, change_type, validation, traceability, implementation."""
        cr = _make_full_cr(status=CRStatus.IMPLEMENTED)
        gen = CREvidenceGenerator()
        evidence = gen.generate_to_dict(cr)
        for key in ["schema_version", "cr_id", "timestamp", "status", "change_type",
                     "validation", "traceability", "implementation"]:
            assert key in evidence, f"Missing required field: {key}"

    def test_evidence_has_hash(self):
        """Evidence must contain a sha256 hash."""
        cr = _make_full_cr(status=CRStatus.IMPLEMENTED)
        gen = CREvidenceGenerator()
        evidence = gen.generate_to_dict(cr)
        assert evidence["hash"].startswith("sha256:")

    def test_bugfix_evidence_includes_regression_ids(self):
        """Bugfix evidence must include regression_verification_ids — C-PROCESS §H.3."""
        cr = _make_full_cr(
            status=CRStatus.IMPLEMENTED,
            change_type=ChangeType.BUGFIX,
            linkage_type=RequirementLinkageType.EXISTING_REF,
            verifications=["TC-SVT-012"],
            root_cause=RootCauseCategory.IMPL_BUG,
        )
        gen = CREvidenceGenerator()
        evidence = gen.generate_to_dict(cr)
        assert evidence["change_type"] == "bugfix"
        assert "regression_verification_ids" in evidence
        assert "TC-SVT-012" in evidence["regression_verification_ids"]
        assert evidence["root_cause_category"] == "impl_bug"

    def test_evidence_file_written(self, tmp_path):
        """Evidence generator writes a JSON file."""
        cr = _make_full_cr(status=CRStatus.IMPLEMENTED)
        gen = CREvidenceGenerator(evidence_dir=tmp_path / "evidence")
        path = gen.generate(cr)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["schema_version"] == "CCC-1.1.0"
        assert data["cr_id"] == cr.id

    def test_evidence_with_verification_results(self):
        """Evidence includes verification_results when provided."""
        cr = _make_full_cr(status=CRStatus.VERIFIED)
        vr = VerificationResult(
            verification_case_id="TC-SVT-012",
            result="PASS",
            executed_at=datetime.now(timezone.utc),
            output="All tests passed",
            validates=["SW-REQ-001"],
        )
        gen = CREvidenceGenerator()
        evidence = gen.generate_to_dict(cr, verification_results=[vr])
        assert len(evidence["verification_results"]) == 1
        assert evidence["verification_results"][0]["result"] == "PASS"


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _make_full_cr(
    status: CRStatus = CRStatus.SUBMITTED,
    change_type: ChangeType = ChangeType.FEATURE,
    linkage_type: RequirementLinkageType | None = None,
    verifications: list[str] | None = None,
    root_cause: RootCauseCategory | None = None,
) -> ChangeRequest:
    """Build a CR that satisfies all fields through IMPLEMENTED."""
    cr = ChangeRequest(
        id="CR-001",
        title="Test CR with enough characters",
        status=status,
        created=datetime.now(timezone.utc),
        requester="dev@example.com",
        problem="A" * 50,
        justification="B" * 20,
        change_type=change_type,
        requirement_linkage_type=linkage_type,
        impact_level=[ImpactLevel.SW],
        requirement_refs=["SW-REQ-001"],
        safety_impact=SafetyImpact.NONE,
        reviewer="lead@example.com",
        approval_date=datetime.now(timezone.utc),
        affected_files=["src/auth.py"],
        affected_verifications=verifications or ["TC-SVT-012"],
        commits=["abc123"],
        evidence_refs=["changes/evidence/CR-001_20260419_120000.json"],
        root_cause_category=root_cause,
    )
    return cr
