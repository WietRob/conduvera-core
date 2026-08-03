"""Compliance Retry Flow Tests v0.18.1

Testet:
1. Dreamer retry compliant -> status=WAITING gesetzt (kein manueller Reset)
2. Researcher retry compliant -> status=WAITING
3. Researcher retry noncompliant -> HOLD_FOR_BOSS
4. Dreamer retry noncompliant -> HOLD_FOR_BOSS
5. Candidate GREEN priority mit gueltigem slug -> pass (slug parser)
6. Candidate slug 'green' -> forbidden_slug=true
7. stop_after_phase bleibt aktiv
8. no Builder in R->D-only
9. no PR in R->D-only
10. Compliance skip when not required
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path.home() / ".hermes/scripts"))

import peekxd_buildroom_loop_v18_1 as v18_1
from peekxd_buildroom_loop_v18_1 import BuildroomOrchestrator


def make_orchestrator(tmp_path, state_overrides=None):
    state_path = Path(tmp_path) / "orchestrator-state.json"
    evidence_dir = Path(tmp_path) / "evidence"

    with patch.object(v18_1, "STATE_FILE", state_path):
        with patch.object(v18_1, "EVIDENCE_DIR", evidence_dir):
            o = BuildroomOrchestrator()

    base_state = {
        "cycle": 20,
        "phase": "DREAMER",
        "status": "RETRYING_COMPLIANCE",
        "mode": "RESEARCHER_DREAMER_ONLY",
        "stop_after_phase": "DREAMER",
        "compliance_required": True,
        "directive_file": None,
        "strategy_file": None,
        "current_candidate": None,
        "pr_open": None,
        "task_ids": {"RESEARCHER": "t_r_test", "DREAMER": "t_d_test"},
        "attempts": {},
        "compliance_retries": {"DREAMER": 1},
    }
    if state_overrides:
        base_state.update(state_overrides)
    o.state = base_state
    o.safety_checks = MagicMock(return_value={
        "main_green": True,
        "open_prs": True,
        "active_builders": True,
        "no_revert_policy": True,
        "no_revert_missing_profiles": [],
    })
    return o, state_path, evidence_dir


def write_evidence(evidence_dir, phase, cycle, content):
    d = evidence_dir / phase
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{phase}-cycle-{cycle}-20260626.md"
    p.write_text(content)
    return p


class TestDreamerRetryFlow:
    """Test DREAMER retry completion path."""

    def test_retry_compliant_sets_waits(self, tmp_path):
        """Test 1: Dreamer retry with compliant evidence sets status=WAITING."""
        o, state_path, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "dreamer", 20,
            "## Candidate 1: `safety-moat-mcp-mw` — GREEN\n"
            "epic: Epic 1 safety moat mcp exposition\n"
            "## Candidate 2: `snapshotstore-skel` — GREEN\n"
            "epic: Epic 2 snapshot element id skeleton\n"
            "## Candidate 3: `at-spi` — YELLOW\nepic: Epic 3\n"
            "## Candidate 4: `wayland` — YELLOW\nepic: Epic 4\n"
            "## Candidate 5: `extra` — GREEN\nepic: Epic 3\n")

        with patch.object(o, "acquire_lock", return_value=True), \
             patch.object(o, "release_lock"), \
             patch.object(o, "reconcile_state"), \
             patch.object(o, "kanban_check_task", return_value=("done", "")), \
             patch.object(v18_1, "STATE_FILE", state_path), \
             patch.object(v18_1, "EVIDENCE_DIR", ed), \
             patch.object(v18_1, "REPO_PATH", tmp_path):
            o.run()

        assert o.state["status"] == "WAITING", (
            f"Expected WAITING, got {o.state['status']}"
        )

    def test_retry_noncompliant_hold_for_boss(self, tmp_path):
        """Test 4: Dreamer retry non-compliant -> HOLD_FOR_BOSS."""
        o, state_path, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "dreamer", 20,
            "## Just window key bugs\nNo safety moat, no snapshot.\n"
            "## Candidate 1: `fix` — GREEN\n")

        with patch.object(o, "acquire_lock", return_value=True), \
             patch.object(o, "release_lock"), \
             patch.object(o, "reconcile_state"), \
             patch.object(o, "kanban_check_task", return_value=("done", "")), \
             patch.object(v18_1, "STATE_FILE", state_path), \
             patch.object(v18_1, "EVIDENCE_DIR", ed), \
             patch.object(v18_1, "REPO_PATH", tmp_path):
            o.run()

        assert o.state["status"] == "HOLD_FOR_BOSS"


class TestResearcherRetryFlow:
    """Test RESEARCHER retry completion path."""

    def test_retry_compliant_sets_waits(self, tmp_path):
        """Test 2: Researcher retry compliant -> WAITING."""
        o, state_path, ed = make_orchestrator(tmp_path, {
            "phase": "RESEARCHER", "status": "RETRYING_COMPLIANCE",
            "compliance_retries": {"RESEARCHER": 1},
        })
        ev = write_evidence(ed, "researcher", 20,
            "## Directive Compliance\n"
            "Safety-Moat MCP-Exposition\nSnapshot/Element-ID Core\n"
            "AT-SPI2 Action-First\nWayland/WSLg Hardening\n\n"
            "### Epic 1 — Safety-Moat MCP-Exposition\n"
            "Finding: ghost audit zone integration with mcp server safety.\n"
            "### Epic 2 — Snapshot/Element-ID Core\n"
            "Finding: snapshot store skeleton location.\n"
            "### Epic 3 — AT-SPI2 Action-First\n"
            "Finding: set-value opportunities.\n"
            "### Epic 4 — Wayland/WSLg Hardening\n"
            "Finding: grim slurp paths.\n")

        with patch.object(o, "acquire_lock", return_value=True), \
             patch.object(o, "release_lock"), \
             patch.object(o, "reconcile_state"), \
             patch.object(o, "kanban_check_task", return_value=("done", "")), \
             patch.object(v18_1, "STATE_FILE", state_path), \
             patch.object(v18_1, "EVIDENCE_DIR", ed), \
             patch.object(v18_1, "REPO_PATH", tmp_path):
            o.run()

        assert o.state["status"] == "WAITING"

    def test_retry_noncompliant_hold_for_boss(self, tmp_path):
        """Test 3: Researcher retry non-compliant -> HOLD_FOR_BOSS."""
        o, state_path, ed = make_orchestrator(tmp_path, {
            "phase": "RESEARCHER", "status": "RETRYING_COMPLIANCE",
            "compliance_retries": {"RESEARCHER": 1},
        })
        ev = write_evidence(ed, "researcher", 20, "## Tactical gaps\nNo epics.")

        with patch.object(o, "acquire_lock", return_value=True), \
             patch.object(o, "release_lock"), \
             patch.object(o, "reconcile_state"), \
             patch.object(o, "kanban_check_task", return_value=("done", "")), \
             patch.object(v18_1, "STATE_FILE", state_path), \
             patch.object(v18_1, "EVIDENCE_DIR", ed), \
             patch.object(v18_1, "REPO_PATH", tmp_path):
            o.run()

        assert o.state["status"] == "HOLD_FOR_BOSS"


class TestSlugParserRobustness:
    """Test that slug parser handles priority labels correctly."""

    def test_green_priority_valid_slug_passes(self, tmp_path):
        """Test 5: Candidate with GREEN priority and valid slug -> compliant."""
        o, _, ed = make_orchestrator(tmp_path, {"phase": "RESEARCHER"})
        ev = write_evidence(ed, "dreamer", 20,
            "## Candidate 1: `safety-moat-mcp-gw` — GREEN\n"
            "epic: Epic 1 safety moat mcp exposition\n"
            "## Candidate 2: `snapshotstore-skel` — GREEN\n"
            "epic: Epic 2 snapshot skeleton element id\n"
            "## Candidate 3: `at-spi-fix` — YELLOW\nepic: Epic 3\n"
            "## Candidate 4: `wayland-fix` — YELLOW\nepic: Epic 4\n"
            "## Candidate 5: `extra` — GREEN\nepic: Epic 3\n")
        compliant, reason, details = o.validate_dreamer_directive_compliance(ev)
        assert compliant is True, f"Expected True, got {reason}. Details: {details}"

    def test_slug_is_green_fails(self, tmp_path):
        """Test 6: Candidate slug 'green' -> forbidden."""
        o, _, ed = make_orchestrator(tmp_path, {"phase": "RESEARCHER"})
        ev = write_evidence(ed, "dreamer", 20,
            "## Candidate 1: `green` — GREEN\n"
            "epic: Epic 1 safety moat mcp exposition\n"
            "## Candidate 2: `snapshot-skel` — GREEN\n"
            "epic: Epic 2 snapshot skeleton element id\n"
            "## Candidate 3: `at-spi` — YELLOW\nepic: Epic 3\n"
            "## Candidate 4: `wayland` — YELLOW\nepic: Epic 4\n"
            "## Candidate 5: `extra` — GREEN\nepic: Epic 3\n")
        compliant, reason, details = o.validate_dreamer_directive_compliance(ev)
        assert compliant is False
        assert "forbidden slug" in reason.lower()


class TestStopGuardAndNoBuilder:
    """Test that v0.18.1 preserves stop_after_phase and mode gates."""

    def test_stop_after_phase_active(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path)
        o.state["stop_after_phase"] = "DREAMER"
        assert o.should_stop_after_phase("DREAMER") is True

    def test_no_builder_phase_allowed(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path, {"phase": "RESEARCHER"})
        assert o.is_phase_blocked_by_mode("BUILDER") is True
        assert o.is_action_blocked_by_mode("PR_CREATE") is True

    def test_compliance_skips_when_false(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path, {
            "phase": "RESEARCHER", "status": "WAITING",
            "compliance_required": False,
        })
        ev = write_evidence(ed, "researcher", 20, "Just tactical gaps.")

        with patch.object(o, "acquire_lock", return_value=True), \
             patch.object(o, "release_lock"), \
             patch.object(o, "reconcile_state"), \
             patch.object(o, "kanban_check_task", return_value=("done", "")), \
             patch.object(o, "safety_checks", return_value={
                 "main_green": True, "open_prs": True,
                 "active_builders": True, "no_revert_policy": True,
                 "no_revert_missing_profiles": []}), \
             patch.object(v18_1, "STATE_FILE", state_path), \
             patch.object(v18_1, "EVIDENCE_DIR", ed), \
             patch.object(v18_1, "REPO_PATH", tmp_path):
            o.run()
        # With compliance_required=False, skips validation and transitions
        assert o.state["phase"] == "DREAMER"
