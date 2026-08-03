"""Directive-Aware Template Tests v0.17

Testet:
1. directive_file in state wird geladen
2. fehlende spec — researcher body fallback (generic)
3. Researcher task body enthaelt ADR-0006 / Safety-Moat / Epics
4. Researcher task body enthaelt Target Files
5. Dreamer task body enthaelt mindestens 4 Epics
6. Dreamer task body fordert Safety-Moat Candidate
7. Dreamer task body fordert Snapshot Candidate
8. Generic body "Analyze PeekXD for Linux computer-use gaps" kommt bei Directive NICHT vor
9. Generic body kommt bei FEHLENDER Directive vor (Fallback korrekt)
10. stop_after_phase guard unveraendert
11. load_cycle_directive entdeckt spec aus EVIDENCE_DIR
12. load_cycle_directive entdeckt ADRs aus REPO
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path.home() / ".hermes/scripts"))

import peekxd_buildroom_loop_v17 as v17
from peekxd_buildroom_loop_v17 import BuildroomOrchestrator


def make_orchestrator(tmp_path, state_overrides=None):
    """Create a v0.17 orchestrator with temp state file and evidence dir."""
    state_path = Path(tmp_path) / "orchestrator-state.json"
    evidence_dir = Path(tmp_path) / "evidence"

    with patch.object(v17, "STATE_FILE", state_path):
        with patch.object(v17, "EVIDENCE_DIR", evidence_dir):
            o = BuildroomOrchestrator()

    base_state = {
        "cycle": 18,
        "phase": "RESEARCHER",
        "status": "NEXT_CYCLE",
        "mode": "RESEARCHER_DREAMER_ONLY",
        "stop_after_phase": "DREAMER",
        "directive_file": None,
        "strategy_file": None,
        "current_candidate": None,
        "pr_open": None,
        "task_ids": {},
        "attempts": {},
    }
    if state_overrides:
        base_state.update(state_overrides)
    o.state = base_state
    return o, state_path, evidence_dir


class TestDirectiveLoader:
    """Test load_cycle_directive discovery."""

    def test_loads_directive_file_from_state(self, tmp_path):
        spec_path = tmp_path / "my-spec.md"
        spec_path.write_text("# My Epic Spec\nEpic 1: Safety")
        o, _, _ = make_orchestrator(tmp_path, {
            "directive_file": str(spec_path),
        })
        directive = o.load_cycle_directive(18)
        assert "directive_file" in directive
        assert "Epic 1: Safety" in directive["directive_file"]

    def test_loads_strategy_file_from_state(self, tmp_path):
        strat_path = tmp_path / "strategy.md"
        strat_path.write_text("# Strategy v0.4.0")
        o, _, _ = make_orchestrator(tmp_path, {
            "strategy_file": str(strat_path),
        })
        directive = o.load_cycle_directive(18)
        assert "strategy_file" in directive

    def test_missing_file_not_in_directive(self, tmp_path):
        o, _, evidence_dir = make_orchestrator(tmp_path, {
            "directive_file": "/nonexistent/path.md",
        })
        directive = o.load_cycle_directive(18)
        assert "directive_file" not in directive

    def test_discovers_spec_from_evidence_dir_exact(self, tmp_path):
        o, _, evidence_dir = make_orchestrator(tmp_path)
        spec_file = evidence_dir / "cycle-18-v0.4.0-spec.md"
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text("# Cycle 18 Spec\nEpic: Safety-Moat")
        with patch.object(v17, "REPO_PATH", tmp_path), \
             patch.object(v17, "EVIDENCE_DIR", evidence_dir):
            directive = o.load_cycle_directive(18)
        assert "spec" in directive
        assert "Epic: Safety-Moat" in directive["spec"]

    def test_discovers_spec_from_evidence_dir_glob(self, tmp_path):
        o, _, evidence_dir = make_orchestrator(tmp_path)
        spec_file = evidence_dir / "cycle-18-anything.md"
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text("# Fallback spec")
        with patch.object(v17, "REPO_PATH", tmp_path), \
             patch.object(v17, "EVIDENCE_DIR", evidence_dir):
            directive = o.load_cycle_directive(18)
        assert "spec" in directive
        assert "Fallback spec" in directive["spec"]

    def test_empty_directive_when_nothing_found(self, tmp_path):
        o, _, evidence_dir = make_orchestrator(tmp_path)
        with patch.object(v17, "REPO_PATH", tmp_path), \
             patch.object(v17, "EVIDENCE_DIR", evidence_dir):
            directive = o.load_cycle_directive(18)
        assert directive == {}


class TestResearcherBody:
    """Test build_researcher_body with and without directive."""

    def test_strategic_body_contains_epics(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path)
        directive = {"spec": "# v0.4.0 Spec\nSafety-Moat first."}
        body = o.build_researcher_body(18, directive)
        assert "STRATEGIC MISSION" in body
        assert "v0.4.0" in body
        assert "Epic 1" in body
        assert "Epic 2" in body
        assert "Epic 3" in body
        assert "Epic 4" in body
        assert "Safety-Moat" in body

    def test_strategic_body_contains_target_files(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path)
        directive = {"spec": "# Spec"}
        body = o.build_researcher_body(18, directive)
        assert "safety.py" in body
        assert "zones.py" in body
        assert "audit.py" in body
        assert "mcp_server.py" in body
        assert "detector.py" in body
        assert "wayland.py" in body

    def test_strategic_body_no_generic_text(self, tmp_path):
        """Test 9b: with directive, generic Analyze text must NOT appear."""
        o, _, _ = make_orchestrator(tmp_path)
        directive = {"spec": "# Spec"}
        body = o.build_researcher_body(18, directive)
        assert "Analyze the PeekXD codebase for Linux computer-use gaps" not in body

    def test_legacy_body_without_directive(self, tmp_path):
        """Test 9a: without directive, fallback to generic body."""
        o, _, _ = make_orchestrator(tmp_path)
        body = o.build_researcher_body(18, {})
        assert "Analyze the PeekXD codebase for Linux computer-use gaps" in body

    def test_strategic_body_has_minimum_8_findings_requirement(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path)
        directive = {"spec": "# Spec"}
        body = o.build_researcher_body(18, directive)
        assert "Minimum 8 findings" in body or "8 findings" in body

    def test_strategic_body_references_directive_paths(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path, {
            "directive_file": "/path/to/spec.md",
            "strategy_file": "/path/to/adr.md",
        })
        directive = {"spec": "# Spec"}
        body = o.build_researcher_body(18, directive)
        assert "/path/to/spec.md" in body
        assert "/path/to/adr.md" in body


class TestDreamerBody:
    """Test build_dreamer_body with and without directive."""

    def test_strategic_dreamer_body_contains_epics(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path)
        directive = {"spec": "# Spec"}
        body = o.build_dreamer_body(18, "/path/to/research.md", directive)
        assert "Epic 1" in body
        assert "Epic 2" in body
        assert "Epic 3" in body
        assert "Epic 4" in body

    def test_strategic_dreamer_body_requires_safety_moat_candidate(self, tmp_path):
        """Test 6: Dreamer body demands Safety-Moat candidate."""
        o, _, _ = make_orchestrator(tmp_path)
        directive = {"spec": "# Spec"}
        body = o.build_dreamer_body(18, "/path/to/research.md", directive)
        assert "Safety-Moat" in body or "safety" in body.lower()

    def test_strategic_dreamer_body_requires_snapshot_candidate(self, tmp_path):
        """Test 7: Dreamer body demands Snapshot/Element-ID candidate."""
        o, _, _ = make_orchestrator(tmp_path)
        directive = {"spec": "# Spec"}
        body = o.build_dreamer_body(18, "/path/to/research.md", directive)
        assert "Snapshot" in body or "snapshot" in body.lower()

    def test_strategic_dreamer_body_minimum_6_candidates(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path)
        directive = {"spec": "# Spec"}
        body = o.build_dreamer_body(18, "/path/to/research.md", directive)
        assert "Minimum 6 candidates" in body or "6 candidates" in body

    def test_strategic_dreamer_body_minimum_2_green(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path)
        directive = {"spec": "# Spec"}
        body = o.build_dreamer_body(18, "/path/to/research.md", directive)
        assert "2 GREEN" in body or "2 green" in body.lower()

    def test_legacy_dreamer_body_without_directive(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path)
        body = o.build_dreamer_body(18, "/path/to/research.md", {})
        assert "Top 5 candidates" in body
        assert "no color names" in body


class TestStopGuardPreserved:
    """Ensure v0.16 guard is unchanged."""

    def test_should_stop_after_phase_still_works(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path, {"stop_after_phase": "DREAMER"})
        assert o.should_stop_after_phase("DREAMER") is True
        assert o.should_stop_after_phase("BUILDER") is False

    def test_enter_stopped_state_still_works(self, tmp_path):
        o, state_path, _ = make_orchestrator(tmp_path)
        with patch.object(v17, "STATE_FILE", state_path):
            o.enter_stopped_state("DREAMER")
        assert o.state["phase"] == "STOPPED_AFTER_DREAMER"
        assert o.state["status"] == "PROOF_COMPLETE"

    def test_mode_safety_gate_still_works(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path, {"mode": "RESEARCHER_DREAMER_ONLY"})
        assert o.is_phase_blocked_by_mode("BUILDER") is True
        assert o.is_phase_blocked_by_mode("DREAMER") is False


class TestFallbackTemplate:
    """Test that missing directive falls back to legacy template (not error)."""

    def test_researcher_fallback_is_generic(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path)
        body = o.build_researcher_body(18, {})
        assert "Analyze the PeekXD codebase" in body

    def test_dreamer_fallback_is_generic(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path)
        body = o.build_dreamer_body(18, "/path/to/research.md", {})
        assert "Top 5 candidates" in body
        assert "no color names" in body
