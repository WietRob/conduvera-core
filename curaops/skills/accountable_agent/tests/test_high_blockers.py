"""
Tests for HIGH Blocker fixes — Context B v2.1.0

Covers:
- HIGH #2: Formal state machine with transition guards + reset()
- HIGH #1: Bugfix-specific blocking rules from C (B-RULES §3.1, §7.1)
- HIGH #3: pre_flight_check() session gate (B-RULES §5.1)
"""

import json
import shutil
import unittest
from pathlib import Path

from curaops.skills.accountable_agent import (
    AccountableAgentService,
    AgentContext,
    ChangeIntent,
    AccountableChange,
    ACStatus,
    AccountabilityError,
    MissingMandatoryLinkError,
    InvalidACTransitionError,
    submit_change_request,
)
from curaops.skills.change_request import (
    ChangeRequestService,
    CRStatus,
    ChangeType,
    RequirementLinkageType,
    RootCauseCategory,
)


class _Base(unittest.TestCase):
    """Shared setUp/tearDown for B HIGH-blocker tests."""

    def setUp(self):
        self.test_dir = Path(__file__).parent / f"test_high_{self.id()}"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.changes_dir = self.test_dir / "changes"
        self.changes_dir.mkdir(exist_ok=True)
        self.evidence_dir = self.changes_dir / "evidence"
        self.evidence_dir.mkdir(exist_ok=True)

        self.service = AccountableAgentService(
            project_root=self.test_dir,
            changes_path=self.changes_dir,
            evidence_dir=self.evidence_dir,
        )

        self.agent_ctx = AgentContext(
            agent_id="test-001",
            agent_name="TestAgent",
            model="test-model",
            tools_used=["file_edit"],
            session_id="sess-001",
        )

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_and_approve_cr(
        self,
        title="Test CR title long enough",
        description="Test CR problem description",
        requirement_refs=None,
        change_type="feature",
        requirement_linkage_type=None,
    ):
        """Helper: create CR, submit, approve. Returns cr_id."""
        svc = ChangeRequestService(
            changes_dir=self.changes_dir,
            evidence_dir=self.evidence_dir,
        )
        cr = svc.create_cr(
            title=title,
            requester="test",
            problem=description,
            justification="test justification long enough",
            impact_level=["SW"],
            requirement_refs=requirement_refs or ["SW-REQ-001"],
            change_type=change_type,
            requirement_linkage_type=requirement_linkage_type,
        )
        cr = svc.submit_cr(cr.id)
        cr = svc.approve_cr(cr.id, reviewer="tester", comment="ok")
        return cr.id


# ═══════════════════════════════════════════════════════════════════════
# HIGH #2: State Machine — B-PROCESS §C
# ═══════════════════════════════════════════════════════════════════════


class TestStateMachine(_Base):
    """HIGH #2: Formal state machine with transition guards."""

    def test_acstatus_enum_values(self):
        """B-PROCESS §C.1: Four canonical states."""
        self.assertEqual(ACStatus.PENDING.value, "pending")
        self.assertEqual(ACStatus.LINKED.value, "linked")
        self.assertEqual(ACStatus.VALIDATED.value, "validated")
        self.assertEqual(ACStatus.BLOCKED.value, "blocked")

    def test_register_with_links_sets_linked(self):
        """P+L provided → status=linked."""
        cr_id = self._create_and_approve_cr()
        ac = self.service.register_accountable_change(
            agent_context=self.agent_ctx,
            change_intent=ChangeIntent(description="test", change_type="feature"),
            cr_id=cr_id,
            requirement_refs=["SW-REQ-001"],
        )
        self.assertEqual(ac.status, "linked")

    def test_register_without_links_sets_pending(self):
        """No links → status=pending."""
        ac = self.service.register_accountable_change(
            agent_context=self.agent_ctx,
            change_intent=ChangeIntent(description="test", change_type="feature"),
            strict=False,
        )
        self.assertEqual(ac.status, "pending")

    def test_transition_pending_to_linked_via_link_to_cr(self):
        """P → L via link_to_cr()."""
        cr_id = self._create_and_approve_cr()
        ac = self.service.register_accountable_change(
            agent_context=self.agent_ctx,
            change_intent=ChangeIntent(description="test", change_type="feature"),
            cr_id=None,
            requirement_refs=["SW-REQ-001"],
            strict=False,
        )
        self.assertEqual(ac.status, "pending")

        self.service.link_to_cr(ac.accountable_id, cr_id)
        self.assertEqual(ac.status, "linked")

    def test_transition_linked_to_validated(self):
        """L → V via validate_accountability()."""
        cr_id = self._create_and_approve_cr()
        ac = self.service.register_accountable_change(
            agent_context=self.agent_ctx,
            change_intent=ChangeIntent(description="test", change_type="feature"),
            cr_id=cr_id,
            requirement_refs=["SW-REQ-001"],
        )
        result = self.service.validate_accountability(ac.accountable_id)
        self.assertTrue(result["valid"])
        self.assertEqual(ac.status, "validated")

    def test_transition_linked_to_blocked(self):
        """L → B when validation finds issues."""
        ac = self.service.register_accountable_change(
            agent_context=self.agent_ctx,
            change_intent=ChangeIntent(description="test", change_type="feature"),
            cr_id="CR-NONEXISTENT",
            requirement_refs=["SW-REQ-001"],
            strict=False,
        )
        ac.status = "linked"  # Force linked status
        result = self.service.validate_accountability(ac.accountable_id)
        self.assertFalse(result["valid"])
        self.assertEqual(ac.status, "blocked")

    def test_transition_pending_to_blocked(self):
        """P → B when validation fails on pending AC."""
        ac = self.service.register_accountable_change(
            agent_context=self.agent_ctx,
            change_intent=ChangeIntent(description="test", change_type="feature"),
            cr_id="CR-NONEXISTENT",
            requirement_refs=[],
            strict=False,
        )
        self.assertEqual(ac.status, "pending")
        result = self.service.validate_accountability(ac.accountable_id)
        self.assertFalse(result["valid"])
        self.assertEqual(ac.status, "blocked")

    def test_reset_blocked_to_pending(self):
        """B → P via reset(). B-PROCESS §C.3."""
        ac = self.service.register_accountable_change(
            agent_context=self.agent_ctx,
            change_intent=ChangeIntent(description="test", change_type="feature"),
            strict=False,
        )
        # Force blocked
        self.service._transition(ac, "blocked", reason="test block")
        self.assertEqual(ac.status, "blocked")

        # Reset
        ac_reset = self.service.reset(ac.accountable_id)
        self.assertEqual(ac_reset.status, "pending")
        self.assertIsNone(ac_reset.block_reason)

    def test_reset_raises_on_non_blocked(self):
        """reset() raises InvalidACTransitionError on non-blocked AC."""
        ac = self.service.register_accountable_change(
            agent_context=self.agent_ctx,
            change_intent=ChangeIntent(description="test", change_type="feature"),
            cr_id="CR-001",
            requirement_refs=["SW-REQ-001"],
            strict=False,
        )
        self.assertEqual(ac.status, "linked")  # cr_id + refs → linked
        with self.assertRaises(InvalidACTransitionError):
            self.service.reset(ac.accountable_id)

    def test_invalid_transition_validated_to_linked(self):
        """V → L is NOT allowed per §C.2 matrix."""
        ac = self.service.register_accountable_change(
            agent_context=self.agent_ctx,
            change_intent=ChangeIntent(description="test", change_type="feature"),
            strict=False,
        )
        self.service._transition(ac, "linked")
        self.service._transition(ac, "validated")
        with self.assertRaises(InvalidACTransitionError):
            self.service._transition(ac, "linked")

    def test_invalid_transition_validated_to_blocked(self):
        """V → B is NOT allowed per §C.2 matrix (terminal state)."""
        ac = AccountableChange(
            accountable_id="AC-TEST000",
            agent_context=self.agent_ctx,
            change_intent=ChangeIntent(description="t", change_type="feature"),
            status="validated",
        )
        self.service._accountable_changes["AC-TEST000"] = ac
        with self.assertRaises(InvalidACTransitionError):
            self.service._transition(ac, "blocked")

    def test_validated_is_terminal(self):
        """V has no outgoing transitions per §C.2."""
        ac = AccountableChange(
            accountable_id="AC-TERM01",
            agent_context=self.agent_ctx,
            change_intent=ChangeIntent(description="t", change_type="feature"),
            status="validated",
        )
        # V→P, V→L, V→B, V→V all blocked
        for target in ("pending", "linked", "blocked", "validated"):
            self.assertFalse(
                self.service._can_transition(ac, target),
                f"V→{target} should not be allowed",
            )

    def test_blocked_can_only_reset_to_pending(self):
        """B → P is the ONLY allowed transition from blocked."""
        ac = AccountableChange(
            accountable_id="AC-BLOCK1",
            agent_context=self.agent_ctx,
            change_intent=ChangeIntent(description="t", change_type="feature"),
            status="blocked",
        )
        self.assertTrue(self.service._can_transition(ac, "pending"))
        self.assertFalse(self.service._can_transition(ac, "linked"))
        self.assertFalse(self.service._can_transition(ac, "validated"))
        self.assertFalse(self.service._can_transition(ac, "blocked"))


# ═══════════════════════════════════════════════════════════════════════
# HIGH #1: Bugfix-Specific Blocking — B-RULES §3.1, §7.1
# ═══════════════════════════════════════════════════════════════════════


class TestBugfixBlocking(_Base):
    """HIGH #1: Bugfix blocking rules consumed from C."""

    def _create_bugfix_cr(self, requirement_refs, linkage_type=None, approve=True,
                          root_cause=None, affected_verifications=None):
        """Helper: create a bugfix CR with specific attributes."""
        svc = ChangeRequestService(
            changes_dir=self.changes_dir,
            evidence_dir=self.evidence_dir,
        )
        cr = svc.create_cr(
            title="Bugfix CR with a title long enough",
            requester="test",
            problem="Bugfix problem description with enough length",
            justification="Bugfix justification with sufficient length",
            impact_level=["SW"],
            requirement_refs=requirement_refs,
            change_type="bugfix",
            requirement_linkage_type=linkage_type,
        )
        # Set root_cause after creation (not a create_cr param)
        if root_cause:
            from curaops.skills.change_request import RootCauseCategory
            cr.root_cause_category = RootCauseCategory(root_cause)
            svc.persistence.save(cr)
        if affected_verifications:
            cr.affected_verifications = affected_verifications
            svc.persistence.save(cr)
        cr = svc.submit_cr(cr.id)
        if approve:
            cr = svc.approve_cr(cr.id, reviewer="tester", comment="ok")
        return cr.id

    def test_bugfix_without_sw_req_blocked_in_preflight(self):
        """B-RULES §3.1: Bugfix without SW-REQ → BLOCK.
        Create a valid bugfix CR (C requires SW-REF), then call pre_flight_check
        with only SYS-REQ in the working refs — B's bugfix gate catches this."""
        cr_id = self._create_bugfix_cr(
            requirement_refs=["SYS-REQ-001", "SW-REQ-001"],
            linkage_type="existing_ref",
        )
        # B's pre_flight_check with bugfix type, only SYS-REQ in working set
        result = self.service.pre_flight_check(
            cr_id=cr_id,
            requirement_refs=["SYS-REQ-001"],
            change_type="bugfix",
        )
        self.assertFalse(result["passed"])
        self.assertTrue(
            any("no SW-REQ linkage" in b for b in result["blocks"])
        )

    def test_bugfix_with_sw_req_passes_preflight(self):
        """Bugfix with SW-REQ present → passes."""
        cr_id = self._create_bugfix_cr(
            requirement_refs=["SW-REQ-001"],
            linkage_type="existing_ref",
        )
        result = self.service.pre_flight_check(
            cr_id=cr_id,
            requirement_refs=["SW-REQ-001"],
            change_type="bugfix",
        )
        self.assertTrue(result["passed"])

    def test_bugfix_implemented_without_verifications_blocked(self):
        """C-RULES §9.4 / B-RULES §7.1: Bugfix at IMPLEMENTED without VerificationCases → BLOCK.
        C enforces affected_verifications as mandatory for IMPLEMENTED, but B provides
        defense-in-depth: if somehow a CR reaches IMPLEMENTED without verifications,
        B's validate_accountability catches it."""
        cr_id = self._create_bugfix_cr(
            requirement_refs=["SW-REQ-001"],
            linkage_type="existing_ref",
            affected_verifications=["TC-SVT-001"],  # needed to pass C's IMPLEMENTED gate
        )
        # Advance CR to IMPLEMENTED (C requires affected_verifications)
        svc = ChangeRequestService(
            changes_dir=self.changes_dir,
            evidence_dir=self.evidence_dir,
        )
        cr = svc.start_cr(cr_id)
        cr = svc.complete_cr(cr_id, affected_files=["a.py"], commits=["abc"])

        # Now simulate the edge case: clear verifications after IMPLEMENTED
        cr.affected_verifications = []
        svc.persistence.save(cr)

        # Register AC and validate — B should catch the missing verifications
        # strict=False: bypass pre-flight gate (CR is IMPLEMENTED, not APPROVED)
        ac = self.service.register_accountable_change(
            agent_context=self.agent_ctx,
            change_intent=ChangeIntent(description="bugfix", change_type="bugfix"),
            cr_id=cr_id,
            requirement_refs=["SW-REQ-001"],
            strict=False,
        )
        result = self.service.validate_accountability(ac.accountable_id)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("no VerificationCases" in i for i in result["issues"])
        )

    def test_bugfix_implemented_with_verifications_passes(self):
        """Bugfix at IMPLEMENTED WITH VerificationCases → passes validation."""
        cr_id = self._create_bugfix_cr(
            requirement_refs=["SW-REQ-001"],
            linkage_type="existing_ref",
            affected_verifications=["TC-SVT-001"],
        )
        svc = ChangeRequestService(
            changes_dir=self.changes_dir,
            evidence_dir=self.evidence_dir,
        )
        svc.start_cr(cr_id)
        svc.complete_cr(cr_id, affected_files=["a.py"], commits=["abc"])

        # strict=False: bypass pre-flight gate (CR is IMPLEMENTED, not APPROVED)
        ac = self.service.register_accountable_change(
            agent_context=self.agent_ctx,
            change_intent=ChangeIntent(description="bugfix", change_type="bugfix"),
            cr_id=cr_id,
            requirement_refs=["SW-REQ-001"],
            strict=False,
        )
        result = self.service.validate_accountability(ac.accountable_id)
        self.assertTrue(result["valid"])

    def test_non_bugfix_ignores_bugfix_rules(self):
        """Feature CR should NOT trigger bugfix blocking."""
        cr_id = self._create_and_approve_cr(
            requirement_refs=["SW-REQ-001"],
            change_type="feature",
        )
        result = self.service.pre_flight_check(
            cr_id=cr_id,
            requirement_refs=["SW-REQ-001"],
            change_type="feature",
        )
        # No bugfix block should be present
        bugfix_blocks = [
            b for b in result["blocks"]
            if "SW-REQ linkage" in b
        ]
        self.assertEqual(len(bugfix_blocks), 0)

    def test_bugfix_warnings_include_root_cause(self):
        """Bugfix without root_cause_category → warning (not block)."""
        cr_id = self._create_bugfix_cr(
            requirement_refs=["SW-REQ-001"],
            linkage_type="existing_ref",
            root_cause=None,
        )
        result = self.service.pre_flight_check(
            cr_id=cr_id,
            requirement_refs=["SW-REQ-001"],
            change_type="bugfix",
        )
        # Should pass (warnings don't block)
        self.assertTrue(result["passed"])
        # Should have root-cause warning
        self.assertTrue(
            any("Root-cause" in w for w in result["warnings"])
        )

    def test_bugfix_new_ref_blocked(self):
        """B-RULES §3.1: Bugfix with new_ref → BLOCK (SW-REQ not APPROVED).
        C-RULES §9.3: new_ref linkage means new SW-REQ must be APPROVED.
        B enforces this as a hard block per B-RULES §3.1 hard block list."""
        cr_id = self._create_bugfix_cr(
            requirement_refs=["SW-REQ-099"],
            linkage_type="new_ref",
        )
        result = self.service.pre_flight_check(
            cr_id=cr_id,
            requirement_refs=["SW-REQ-099"],
            change_type="bugfix",
        )
        self.assertFalse(result["passed"])
        self.assertTrue(
            any("not APPROVED" in b for b in result["blocks"])
        )

    def test_bugfix_existing_ref_not_blocked(self):
        """B-RULES §3.1: Bugfix with existing_ref does NOT trigger §9.3 block.
        Only new_ref triggers the SW-REQ APPROVAL block."""
        cr_id = self._create_bugfix_cr(
            requirement_refs=["SW-REQ-001"],
            linkage_type="existing_ref",
        )
        result = self.service.pre_flight_check(
            cr_id=cr_id,
            requirement_refs=["SW-REQ-001"],
            change_type="bugfix",
        )
        # No §9.3 block should be present
        s93_blocks = [
            b for b in result["blocks"]
            if "not APPROVED" in b
        ]
        self.assertEqual(len(s93_blocks), 0)

    def test_bugfix_cr_with_root_cause_no_warning(self):
        """Bugfix WITH root_cause_category → no root-cause warning."""
        cr_id = self._create_bugfix_cr(
            requirement_refs=["SW-REQ-001"],
            linkage_type="existing_ref",
            root_cause="impl_bug",
        )
        result = self.service.pre_flight_check(
            cr_id=cr_id,
            requirement_refs=["SW-REQ-001"],
            change_type="bugfix",
        )
        self.assertTrue(result["passed"])
        self.assertFalse(
            any("Root-cause" in w for w in result["warnings"])
        )


# ═══════════════════════════════════════════════════════════════════════
# HIGH #3: Pre-Flight Check — B-RULES §5.1, B-PROCESS §D.1
# ═══════════════════════════════════════════════════════════════════════


class TestPreFlightCheck(_Base):
    """HIGH #3: pre_flight_check() session gate."""

    def test_preflight_passes_with_approved_cr_and_refs(self):
        """All checks pass → passed=True."""
        cr_id = self._create_and_approve_cr()
        result = self.service.pre_flight_check(
            cr_id=cr_id,
            requirement_refs=["SW-REQ-001"],
        )
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["blocks"]), 0)

    def test_preflight_blocks_nonexistent_cr(self):
        """CR not found → block."""
        result = self.service.pre_flight_check(
            cr_id="CR-999",
            requirement_refs=["SW-REQ-001"],
        )
        self.assertFalse(result["passed"])
        self.assertTrue(
            any("does not exist" in b for b in result["blocks"])
        )

    def test_preflight_blocks_non_approved_cr(self):
        """CR status ≠ APPROVED → block. B-RULES §3.1."""
        svc = ChangeRequestService(
            changes_dir=self.changes_dir,
            evidence_dir=self.evidence_dir,
        )
        cr = svc.create_cr(
            title="Draft CR with long enough title",
            requester="test",
            problem="x" * 50,
            justification="x" * 20,
            impact_level=["SW"],
            requirement_refs=["SW-REQ-001"],
        )
        # Leave in DRAFT (not submitted/approved)

        result = self.service.pre_flight_check(
            cr_id=cr.id,
            requirement_refs=["SW-REQ-001"],
        )
        self.assertFalse(result["passed"])
        self.assertTrue(
            any("must be APPROVED" in b for b in result["blocks"])
        )

    def test_preflight_blocks_empty_requirement_refs(self):
        """No requirement refs → block. B-RULES §3.1."""
        cr_id = self._create_and_approve_cr()
        result = self.service.pre_flight_check(
            cr_id=cr_id,
            requirement_refs=[],
        )
        self.assertFalse(result["passed"])
        self.assertTrue(
            any("No requirement refs" in b for b in result["blocks"])
        )

    def test_preflight_blocks_invalid_id_format(self):
        """Invalid requirement ID format → block. B-RULES §3.1."""
        cr_id = self._create_and_approve_cr()
        result = self.service.pre_flight_check(
            cr_id=cr_id,
            requirement_refs=["INVALID-REF", "ALSO-BAD"],
        )
        self.assertFalse(result["passed"])
        self.assertTrue(
            any("Invalid ID format" in b for b in result["blocks"])
        )

    def test_preflight_blocks_sys_impact_without_sys_req(self):
        """SYS impact but no SYS-REQ → block. B-RULES §4."""
        cr_id = self._create_and_approve_cr()
        result = self.service.pre_flight_check(
            cr_id=cr_id,
            requirement_refs=["SW-REQ-001"],
            impact_level=["SYS", "SW"],
        )
        self.assertFalse(result["passed"])
        self.assertTrue(
            any("no SYS-REQ" in b for b in result["blocks"])
        )

    def test_preflight_blocks_arch_impact_without_sw_arch(self):
        """ARCH impact but no SW-ARCH → block. B-RULES §3."""
        cr_id = self._create_and_approve_cr()
        result = self.service.pre_flight_check(
            cr_id=cr_id,
            requirement_refs=["SW-REQ-001"],
            impact_level=["ARCH", "SW"],
        )
        self.assertFalse(result["passed"])
        self.assertTrue(
            any("no SW-ARCH" in b for b in result["blocks"])
        )

    def test_preflight_passes_with_sys_impact_and_sys_req(self):
        """SYS impact + SYS-REQ present → passes."""
        cr_id = self._create_and_approve_cr(
            requirement_refs=["SYS-REQ-001", "SW-REQ-001"],
        )
        result = self.service.pre_flight_check(
            cr_id=cr_id,
            requirement_refs=["SYS-REQ-001", "SW-REQ-001"],
            impact_level=["SYS", "SW"],
        )
        self.assertTrue(result["passed"])

    def test_preflight_returns_blocks_and_warnings_separately(self):
        """Result dict has 'blocks' and 'warnings' as separate lists."""
        cr_id = self._create_and_approve_cr()
        result = self.service.pre_flight_check(
            cr_id=cr_id,
            requirement_refs=["SW-REQ-001"],
        )
        self.assertIn("passed", result)
        self.assertIn("blocks", result)
        self.assertIn("warnings", result)
        self.assertIsInstance(result["blocks"], list)
        self.assertIsInstance(result["warnings"], list)

    def test_preflight_valid_id_formats_accepted(self):
        """Valid SW-REQ, SYS-REQ, SW-ARCH, SEC-REQ all accepted."""
        cr_id = self._create_and_approve_cr(
            requirement_refs=["SW-REQ-001", "SYS-REQ-001",
                              "SW-ARCH-001", "SEC-REQ-001"],
        )
        result = self.service.pre_flight_check(
            cr_id=cr_id,
            requirement_refs=["SW-REQ-001", "SYS-REQ-001",
                              "SW-ARCH-001", "SEC-REQ-001"],
        )
        self.assertTrue(result["passed"])


# ═══════════════════════════════════════════════════════════════════════
# Integration: Reset + Validate Cycle
# ═══════════════════════════════════════════════════════════════════════


class TestResetValidateCycle(_Base):
    """B→P reset → fix → re-validate cycle."""

    def test_blocked_reset_link_validate_cycle(self):
        """
        Full cycle: register (no links) → validate (blocked) →
        reset (pending) → link CR + refs → validate (validated).
        """
        # Register without links
        ac = self.service.register_accountable_change(
            agent_context=self.agent_ctx,
            change_intent=ChangeIntent(description="cycle test", change_type="feature"),
            strict=False,
        )
        self.assertEqual(ac.status, "pending")

        # Validate → blocked (no CR, no refs)
        result = self.service.validate_accountability(ac.accountable_id)
        self.assertFalse(result["valid"])
        self.assertEqual(ac.status, "blocked")

        # Reset
        self.service.reset(ac.accountable_id)
        self.assertEqual(ac.status, "pending")

        # Now create CR and link
        cr_id = self._create_and_approve_cr()
        # Set refs BEFORE linking (link_to_cr checks refs for P→L transition)
        ac.requirement_refs = ["SW-REQ-001"]
        self.service.link_to_cr(ac.accountable_id, cr_id)
        # Status should be "linked" now (link_to_cr transitions P→L)
        self.assertEqual(ac.status, "linked")

        # Validate again → should pass
        result = self.service.validate_accountability(ac.accountable_id)
        self.assertTrue(result["valid"])
        self.assertEqual(ac.status, "validated")


# ═══════════════════════════════════════════════════════════════════════
# HIGH #3b: Pre-flight Gate Wired Into Registration
# ═══════════════════════════════════════════════════════════════════════


class TestPreFlightGateInRegistration(_Base):
    """Prove pre_flight_check is a real gate wired into register_accountable_change."""

    def test_register_strict_blocks_when_cr_not_approved(self):
        """register_accountable_change(strict=True) with non-APPROVED CR → BLOCK.
        Proves pre-flight gate fires during registration."""
        svc = ChangeRequestService(
            changes_dir=self.changes_dir,
            evidence_dir=self.evidence_dir,
        )
        cr = svc.create_cr(
            title="Draft CR long enough for title validation",
            requester="test",
            problem="x" * 50,
            justification="x" * 20,
            impact_level=["SW"],
            requirement_refs=["SW-REQ-001"],
        )
        # Leave in DRAFT — not approved

        with self.assertRaises(MissingMandatoryLinkError) as ctx:
            self.service.register_accountable_change(
                agent_context=self.agent_ctx,
                change_intent=ChangeIntent(description="test", change_type="feature"),
                cr_id=cr.id,
                requirement_refs=["SW-REQ-001"],
                strict=True,
            )
        self.assertIn("Pre-flight gate BLOCKED", str(ctx.exception))
        self.assertIn("must be APPROVED", str(ctx.exception))

    def test_register_strict_blocks_nonexistent_cr(self):
        """register_accountable_change(strict=True) with missing CR → BLOCK.
        Pre-flight catches CR-not-found during registration."""
        with self.assertRaises(MissingMandatoryLinkError) as ctx:
            self.service.register_accountable_change(
                agent_context=self.agent_ctx,
                change_intent=ChangeIntent(description="test", change_type="feature"),
                cr_id="CR-NONEXISTENT",
                requirement_refs=["SW-REQ-001"],
                strict=True,
            )
        self.assertIn("Pre-flight gate BLOCKED", str(ctx.exception))

    def test_register_strict_passes_with_approved_cr(self):
        """register_accountable_change(strict=True) with valid APPROVED CR → passes.
        Pre-flight gate allows registration when all checks pass."""
        cr_id = self._create_and_approve_cr()
        ac = self.service.register_accountable_change(
            agent_context=self.agent_ctx,
            change_intent=ChangeIntent(description="test", change_type="feature"),
            cr_id=cr_id,
            requirement_refs=["SW-REQ-001"],
            strict=True,
        )
        self.assertEqual(ac.status, "linked")
        self.assertEqual(ac.cr_id, cr_id)

    def test_register_non_strict_skips_preflight_gate(self):
        """register_accountable_change(strict=False) skips pre-flight gate.
        Non-strict mode allows registration even with invalid CR.
        Status is 'linked' because cr_id+requirement_refs are present."""
        ac = self.service.register_accountable_change(
            agent_context=self.agent_ctx,
            change_intent=ChangeIntent(description="test", change_type="feature"),
            cr_id="CR-NONEXISTENT",
            requirement_refs=["SW-REQ-001"],
            strict=False,
        )
        # strict=False skips pre-flight gate → registration succeeds
        # status='linked' because both cr_id and requirement_refs are present
        self.assertEqual(ac.status, "linked")
        self.assertEqual(ac.cr_id, "CR-NONEXISTENT")

