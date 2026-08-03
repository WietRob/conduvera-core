"""Directive Compliance Gate Tests v0.18

Testet:
1. Researcher Evidence ohne Safety-Moat => fail
2. Researcher Evidence ohne Snapshot => fail
3. Researcher Evidence mit 4 Epics => pass
4. Researcher Evidence nur taktisch => fail
5. Dreamer Evidence ohne Safety Candidate => fail
6. Dreamer Evidence ohne Snapshot Candidate => fail
7. Dreamer Evidence mit 2 GREEN + Safety + Snapshot => pass
8. Invalid slug => fail
9. Noncompliance blocks transition
10. Compliance retry creates new task
11. Max retry => HOLD_FOR_BOSS
12. stop_after_phase remains active
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path.home() / ".hermes/scripts"))

import peekxd_buildroom_loop_v18 as v18
from peekxd_buildroom_loop_v18 import BuildroomOrchestrator


def make_orchestrator(tmp_path, state_overrides=None):
    state_path = Path(tmp_path) / "orchestrator-state.json"
    evidence_dir = Path(tmp_path) / "evidence"

    with patch.object(v18, "STATE_FILE", state_path):
        with patch.object(v18, "EVIDENCE_DIR", evidence_dir):
            o = BuildroomOrchestrator()

    base_state = {
        "cycle": 19,
        "phase": "RESEARCHER",
        "status": "WAITING",
        "mode": "RESEARCHER_DREAMER_ONLY",
        "stop_after_phase": "DREAMER",
        "compliance_required": True,
        "directive_required": True,
        "directive_file": None,
        "strategy_file": None,
        "current_candidate": None,
        "pr_open": None,
        "task_ids": {"RESEARCHER": "t_r_test"},
        "attempts": {},
        "compliance_retries": {},
    }
    if state_overrides:
        base_state.update(state_overrides)
    o.state = base_state
    return o, state_path, evidence_dir


def write_evidence(evidence_dir, phase, cycle, content):
    d = evidence_dir / phase
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{phase}-cycle-{cycle}-20260626.md"
    p.write_text(content)
    return p


# ── Researcher Compliance Tests ─────────────────────────────────────────

class TestResearcherCompliance:
    """Test validate_researcher_directive_compliance()."""

    def test_no_safety_moat_fails(self, tmp_path):
        o, _, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "researcher", 19,
            "## Directive Compliance\nJust window key bugs.")
        compliant, reason, hits = o.validate_researcher_directive_compliance(ev)
        assert compliant is False
        assert "only 0/4 epics" in reason
        assert hits.get("safety-moat mcp") is False

    def test_no_snapshot_fails(self, tmp_path):
        o, _, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "researcher", 19,
            "## Directive Compliance\nsafety-moat mcp ghost zones audit — yes."
            "\n### Epic 1 — Safety-Moat MCP-Exposition\nFinding: ghost/zone integration.")
        compliant, reason, hits = o.validate_researcher_directive_compliance(ev)
        assert compliant is False
        assert "only 1/4 epics" in reason
        assert hits.get("snapshot-element-id") is False

    def test_four_epics_passes(self, tmp_path):
        o, _, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "researcher", 19,
            "## Directive Compliance\n"
            "Safety-Moat MCP-Exposition\nSnapshot/Element-ID Core\n"
            "AT-SPI2 Action-First\nWayland/WSLg Hardening\n\n"
            "### Epic 1 — Safety-Moat MCP-Exposition\n"
            "Finding: ghost audit zone integration with snapshot.\n"
            "### Epic 2 — Snapshot/Element-ID Core\n"
            "Finding: SnapshotStore skeleton location.\n"
            "### Epic 3 — AT-SPI2 Action-First\n"
            "Finding: set-value opportunities.\n"
            "### Epic 4 — Wayland/WSLg Hardening\n"
            "Finding: grim slurp paths.\n")
        compliant, reason, hits = o.validate_researcher_directive_compliance(ev)
        assert compliant is True, f"Expected True, got {reason}"

    def test_pure_tactical_fails(self, tmp_path):
        o, _, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "researcher", 19,
            "## Findings\n1. Window key contract mismatch.\n"
            "2. Fallback emits capture_screen.\n"
            "3. MCP doctor tool count drift.\n"
            "4. Examples screenshot call site broken.\n"
            "5. README stale claims.\n"
            "6. Apostrophe escaping bug.\n")
        compliant, reason, _ = o.validate_researcher_directive_compliance(ev)
        assert compliant is False
        assert "no 'Directive Compliance'" in reason or "only 0/4 epics" in reason


# ── Dreamer Compliance Tests ────────────────────────────────────────────

class TestDreamerCompliance:
    """Test validate_dreamer_directive_compliance()."""

    def test_no_safety_candidate_fails(self, tmp_path):
        o, _, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "dreamer", 19,
            "## Candidate 1: `window-fix` — GREEN\n"
            "epic: Epic 3\n"
            "## Candidate 2: `snapshot-skeleton` — GREEN\n"
            "epic: Epic 2 snapshot store\n"
            "## Candidate 3: `at-spi-fix` — YELLOW\nepic: Epic 3\n"
            "## Candidate 4: `wayland-fix` — YELLOW\nepic: Epic 4\n"
            "## Candidate 5: `extra-fix` — GREEN\nepic: Epic 3\n")
        compliant, reason, details = o.validate_dreamer_directive_compliance(ev)
        assert compliant is False
        assert "safety" in reason.lower() or details["safety_moat"] is False

    def test_no_snapshot_candidate_fails(self, tmp_path):
        o, _, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "dreamer", 19,
            "## Candidate 1: `window-fix` — GREEN\n"
            "epic: Epic 3\n"
            "## Candidate 2: `safety-moat-mcp-mw` — GREEN\n"
            "epic: Epic 1 safety moat mcp exposition\n"
            "## Candidate 3: `at-spi-fix` — YELLOW\nepic: Epic 3\n"
            "## Candidate 4: `wayland-fix` — YELLOW\nepic: Epic 4\n"
            "## Candidate 5: `extra-fix` — GREEN\nepic: Epic 3\n")
        compliant, reason, details = o.validate_dreamer_directive_compliance(ev)
        assert compliant is False
        assert "snapshot" in reason.lower() or details["snapshot"] is False

    def test_green_safety_snapshot_passes(self, tmp_path):
        o, _, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "dreamer", 19,
            "## Candidate 1: `safety-moat-mcp-middleware` — GREEN\n"
            "epic: Epic 1 Safety-Moat MCP-Exposition\n"
            "## Candidate 2: `snapshotstore-skeleton` — GREEN\n"
            "epic: Epic 2 Snapshot/Element-ID Core\n"
            "## Candidate 3: `at-spi-set-value` — YELLOW\n"
            "epic: Epic 3 AT-SPI2 Action-First\n"
            "## Candidate 4: `wayland-grim-fix` — YELLOW\n"
            "epic: Epic 4 Wayland/WSLg\n"
            "## Candidate 5: `window-key-fix` — GREEN\n"
            "epic: Epic 3\n")
        compliant, reason, details = o.validate_dreamer_directive_compliance(ev)
        assert compliant is True, f"Expected True, got {reason} details={details}"

    def test_invalid_slug_fails(self, tmp_path):
        o, _, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "dreamer", 19,
            "## Candidate 1: `green` — GREEN\n"
            "epic: Epic 1 safety moat mcp exposition\n"
            "## Candidate 2: `snapshot-skeleton` — GREEN\n"
            "epic: Epic 2 snapshot element id\n"
            "## Candidate 3: `at-spi` — YELLOW\nepic: Epic 3\n"
            "## Candidate 4: `wayland` — YELLOW\nepic: Epic 4\n"
            "## Candidate 5: `extra` — GREEN\nepic: Epic 3\n")
        compliant, reason, details = o.validate_dreamer_directive_compliance(ev)
        assert compliant is False
        assert "forbidden slug" in reason.lower()


# ── Compliance Gate Run Tests ───────────────────────────────────────────

class TestComplianceGateRun:
    """Test compliance gate integrated into run() loop."""

    def test_noncompliance_triggers_retry(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path, {
            "phase": "RESEARCHER", "status": "WAITING",
        })
        # Write non-compliant evidence
        ev = write_evidence(ed, "researcher", 19, "## Just tactical gaps\nNo epics.")
        retry_dispatched = [False]

        with patch.object(o, "acquire_lock", return_value=True), \
             patch.object(o, "release_lock"), \
             patch.object(o, "reconcile_state"), \
             patch.object(o, "kanban_check_task", return_value=("done", "")), \
             patch.object(o, "_dispatch_compliance_retry", return_value=None), \
             patch.object(o, "safety_checks", return_value={
                 "main_green": True, "open_prs": True,
                 "active_builders": True, "no_revert_policy": True,
                 "no_revert_missing_profiles": []}), \
             patch.object(v18, "STATE_FILE", state_path), \
             patch.object(v18, "EVIDENCE_DIR", ed), \
             patch.object(v18, "REPO_PATH", tmp_path):
            o.run()
        # Should have set status to RETRYING_COMPLIANCE (not DREAMER)
        assert o.state["phase"] == "RESEARCHER"
        assert o.state["status"] in ("RETRYING_COMPLIANCE", "HOLD_FOR_BOSS")

    def test_max_compliance_retry_hold_for_boss(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path, {
            "phase": "RESEARCHER", "status": "WAITING",
            "compliance_retries": {"RESEARCHER": 1},  # already at max
        })
        ev = write_evidence(ed, "researcher", 19, "## Just tactical gaps\nNo epics.")

        with patch.object(o, "acquire_lock", return_value=True), \
             patch.object(o, "release_lock"), \
             patch.object(o, "reconcile_state"), \
             patch.object(o, "kanban_check_task", return_value=("done", "")), \
             patch.object(o, "safety_checks", return_value={
                 "main_green": True, "open_prs": True,
                 "active_builders": True, "no_revert_policy": True,
                 "no_revert_missing_profiles": []}), \
             patch.object(v18, "STATE_FILE", state_path), \
             patch.object(v18, "EVIDENCE_DIR", ed), \
             patch.object(v18, "REPO_PATH", tmp_path):
            o.run()
        assert o.state["status"] == "HOLD_FOR_BOSS"

    def test_stop_after_phase_still_active(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path, {
            "phase": "DREAMER", "status": "WAITING",
            "stop_after_phase": "DREAMER",
        })
        # Write compliant dreamer evidence
        ev = write_evidence(ed, "dreamer", 19,
            "## Candidate 1: `safety-moat-mcp-mw` — GREEN\n"
            "epic: Epic 1 safety moat mcp exposition\n"
            "## Candidate 2: `snapshotstore-skeleton` — GREEN\n"
            "epic: Epic 2 snapshot element id store skeleton\n"
            "## Candidate 3: `at-spi-action` — YELLOW\nepic: Epic 3\n"
            "## Candidate 4: `wayland-hard` — YELLOW\nepic: Epic 4\n"
            "## Candidate 5: `extra-fix` — GREEN\nepic: Epic 3\n")

        o.state["compliance_required"] = True
        o.state["compliance_retries"] = {}
        o.state["task_ids"]["DREAMER"] = "t_d_test"

        with patch.object(o, "acquire_lock", return_value=True), \
             patch.object(o, "release_lock"), \
             patch.object(o, "reconcile_state"), \
             patch.object(o, "kanban_check_task", return_value=("done", "")), \
             patch.object(o, "safety_checks", return_value={
                 "main_green": True, "open_prs": True,
                 "active_builders": True, "no_revert_policy": True,
                 "no_revert_missing_profiles": []}), \
             patch.object(v18, "STATE_FILE", state_path), \
             patch.object(v18, "EVIDENCE_DIR", ed), \
             patch.object(v18, "REPO_PATH", tmp_path):
            o.run()
        # stop_after_phase=DREAMER should trigger enter_stopped_state
        assert o.state["phase"] == "STOPPED_AFTER_DREAMER"
        assert o.state["status"] == "PROOF_COMPLETE"

    def test_compliance_skips_when_not_required(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path, {
            "phase": "RESEARCHER", "status": "WAITING",
            "compliance_required": False,  # disabled
        })
        ev = write_evidence(ed, "researcher", 19, "## Just tactical\nNo epics at all.")

        with patch.object(o, "acquire_lock", return_value=True), \
             patch.object(o, "release_lock"), \
             patch.object(o, "reconcile_state"), \
             patch.object(o, "kanban_check_task", return_value=("done", "")), \
             patch.object(o, "safety_checks", return_value={
                 "main_green": True, "open_prs": True,
                 "active_builders": True, "no_revert_policy": True,
                 "no_revert_missing_profiles": []}), \
             patch.object(v18, "STATE_FILE", state_path), \
             patch.object(v18, "EVIDENCE_DIR", ed), \
             patch.object(v18, "REPO_PATH", tmp_path):
            o.run()
        # Should skip compliance and transition to DREAMER
        assert o.state["phase"] == "DREAMER"
        assert o.state["status"] == "NEXT_PHASE"
