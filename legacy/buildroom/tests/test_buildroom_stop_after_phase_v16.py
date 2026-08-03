"""stop_after_phase Guard Tests v0.16

Testet:
1. stop_after_phase=DREAMER + Dreamer complete → STOPPED_AFTER_DREAMER
2. stop_after_phase=DREAMER → kein Builder Task
3. mode=RESEARCHER_DREAMER_ONLY blockiert Builder
4. mode=RESEARCHER_DREAMER_ONLY blockiert PR-Erstellung
5. ohne stop_after_phase läuft normal zu Builder
6. stop_after_phase=RESEARCHER stoppt nach Researcher
7. Cron/next run bei STOPPED_AFTER_DREAMER startet nichts
8. mode blockiert Merge
9. stop_after_phase guard in DREAMER completion path
10. enter_stopped_state preserves task_ids
11. should_stop_after_phase mismatch returns False
12. is_action_blocked_by_mode no mode = not blocked
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path.home() / ".hermes/scripts"))

# Import the v0.16 orchestrator
import peekxd_buildroom_loop_v16 as v16
from peekxd_buildroom_loop_v16 import BuildroomOrchestrator


def make_orchestrator(tmpdir, state_overrides=None):
    """Create a v0.16 orchestrator with temp state file."""
    state_path = Path(tmpdir) / "orchestrator-state.json"
    evidence_dir = Path(tmpdir) / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    with patch.object(v16, "STATE_FILE", state_path):
        with patch.object(v16, "EVIDENCE_DIR", evidence_dir):
            o = BuildroomOrchestrator()

    base_state = {
        "cycle": 15,
        "phase": "DREAMER",
        "status": "WAITING",
        "mode": None,
        "stop_after_phase": None,
        "current_candidate": None,
        "pr_open": None,
        "task_ids": {"RESEARCHER": "t_r1", "DREAMER": "t_d1"},
        "attempts": {},
    }
    if state_overrides:
        base_state.update(state_overrides)
    o.state = base_state
    return o, state_path, evidence_dir


class TestShouldStopAfterPhase:
    """Test should_stop_after_phase() predicate."""

    def test_match_returns_true(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path, {"stop_after_phase": "DREAMER"})
        assert o.should_stop_after_phase("DREAMER") is True

    def test_mismatch_returns_false(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path, {"stop_after_phase": "RESEARCHER"})
        assert o.should_stop_after_phase("DREAMER") is False

    def test_no_stop_set_returns_false(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path, {"stop_after_phase": None})
        assert o.should_stop_after_phase("DREAMER") is False

    def test_empty_stop_returns_false(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path, {"stop_after_phase": ""})
        assert o.should_stop_after_phase("DREAMER") is False


class TestEnterStoppedState:
    """Test enter_stopped_state() sets terminal state correctly."""

    def test_sets_stopped_after_dreamer(self, tmp_path):
        o, state_path, _ = make_orchestrator(tmp_path)
        with patch.object(v16, "STATE_FILE", state_path):
            o.enter_stopped_state("DREAMER")
        assert o.state["phase"] == "STOPPED_AFTER_DREAMER"
        assert o.state["status"] == "PROOF_COMPLETE"

    def test_preserves_task_ids(self, tmp_path):
        o, state_path, _ = make_orchestrator(tmp_path)
        with patch.object(v16, "STATE_FILE", state_path):
            o.enter_stopped_state("DREAMER")
        # task_ids must be unchanged
        assert o.state["task_ids"] == {"RESEARCHER": "t_r1", "DREAMER": "t_d1"}

    def test_preserves_attempts(self, tmp_path):
        o, state_path, _ = make_orchestrator(tmp_path)
        with patch.object(v16, "STATE_FILE", state_path):
            o.enter_stopped_state("DREAMER")
        assert o.state.get("attempts") == {}

    def test_stopped_after_researcher(self, tmp_path):
        o, state_path, _ = make_orchestrator(tmp_path, {"task_ids": {"RESEARCHER": "t_r1"}})
        with patch.object(v16, "STATE_FILE", state_path):
            o.enter_stopped_state("RESEARCHER")
        assert o.state["phase"] == "STOPPED_AFTER_RESEARCHER"


class TestModeSafetyGate:
    """Test mode-based blocking of Builder/PR/Merge."""

    def test_restricted_mode_blocks_builder(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path, {"mode": "RESEARCHER_DREAMER_ONLY"})
        assert o.is_phase_blocked_by_mode("BUILDER") is True

    def test_restricted_mode_allows_researcher(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path, {"mode": "RESEARCHER_DREAMER_ONLY"})
        assert o.is_phase_blocked_by_mode("RESEARCHER") is False

    def test_restricted_mode_allows_dreamer(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path, {"mode": "RESEARCHER_DREAMER_ONLY"})
        assert o.is_phase_blocked_by_mode("DREAMER") is False

    def test_restricted_mode_blocks_pr_create(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path, {"mode": "RESEARCHER_DREAMER_ONLY"})
        assert o.is_action_blocked_by_mode("PR_CREATE") is True

    def test_restricted_mode_blocks_merge(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path, {"mode": "RESEARCHER_DREAMER_ONLY"})
        assert o.is_action_blocked_by_mode("MERGE") is True

    def test_no_mode_not_blocked(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path, {"mode": None})
        assert o.is_phase_blocked_by_mode("BUILDER") is False
        assert o.is_action_blocked_by_mode("PR_CREATE") is False
        assert o.is_action_blocked_by_mode("MERGE") is False

    def test_unknown_mode_not_blocked(self, tmp_path):
        o, _, _ = make_orchestrator(tmp_path, {"mode": "FULL_CYCLE"})
        assert o.is_phase_blocked_by_mode("BUILDER") is False


class TestDreamerCompletionGuard:
    """Test that DREAMER completion with stop_after_phase halts before BUILDER."""

    def test_stop_after_dreamer_enters_stopped_state(self, tmp_path):
        """Test 1: stop_after_phase=DREAMER + Dreamer complete → STOPPED_AFTER_DREAMER."""
        o, state_path, evidence_dir = make_orchestrator(
            tmp_path,
            {"mode": "RESEARCHER_DREAMER_ONLY", "stop_after_phase": "DREAMER",
             "phase": "DREAMER", "status": "WAITING"}
        )
        # Create dreamer evidence so check_phase_complete passes
        dreamer_dir = evidence_dir / "dreamer"
        dreamer_dir.mkdir(parents=True, exist_ok=True)
        (dreamer_dir / "dreamer-cycle-15-20260624.md").write_text("# Dreamer evidence\n## Candidate 1: `test-slug` — GREEN")

        # Mock task as done
        with patch.object(o, "kanban_check_task", return_value=("done", "")):
            with patch.object(o, "acquire_lock", return_value=True):
                with patch.object(o, "release_lock"):
                    with patch.object(o, "reconcile_state"):
                        with patch.object(o, "safety_checks", return_value={
                            "main_green": True, "open_prs": True,
                            "active_builders": True, "no_revert_policy": True,
                            "no_revert_missing_profiles": []
                        }):
                            with patch.object(v16, "STATE_FILE", state_path):
                                with patch.object(v16, "EVIDENCE_DIR", evidence_dir):
                                    o.run()

        assert o.state["phase"] == "STOPPED_AFTER_DREAMER"
        assert o.state["status"] == "PROOF_COMPLETE"
        # No builder task created
        assert "BUILDER" not in o.state.get("task_ids", {})

    def test_no_stop_after_dreamer_transitions_to_builder(self, tmp_path):
        """Test 5: without stop_after_phase, normal transition to BUILDER."""
        o, state_path, evidence_dir = make_orchestrator(
            tmp_path,
            {"mode": None, "stop_after_phase": None,
             "phase": "DREAMER", "status": "WAITING"}
        )
        dreamer_dir = evidence_dir / "dreamer"
        dreamer_dir.mkdir(parents=True, exist_ok=True)
        (dreamer_dir / "dreamer-cycle-15-20260624.md").write_text("# Dreamer evidence\n## Candidate 1: `test-slug` — GREEN")

        with patch.object(o, "kanban_check_task", return_value=("done", "")):
            with patch.object(o, "acquire_lock", return_value=True):
                with patch.object(o, "release_lock"):
                    with patch.object(o, "reconcile_state"):
                        with patch.object(o, "safety_checks", return_value={
                            "main_green": True, "open_prs": True,
                            "active_builders": True, "no_revert_policy": True,
                            "no_revert_missing_profiles": []
                        }):
                            with patch.object(v16, "STATE_FILE", state_path):
                                with patch.object(v16, "EVIDENCE_DIR", evidence_dir):
                                    o.run()

        assert o.state["phase"] == "BUILDER"
        assert o.state["status"] == "NEXT_PHASE"

    def test_mode_blocks_builder_after_dreamer(self, tmp_path):
        """Test 3: mode=RESEARCHER_DREAMER_ONLY blocks transition to BUILDER."""
        o, state_path, evidence_dir = make_orchestrator(
            tmp_path,
            {"mode": "RESEARCHER_DREAMER_ONLY", "stop_after_phase": None,
             "phase": "DREAMER", "status": "WAITING"}
        )
        dreamer_dir = evidence_dir / "dreamer"
        dreamer_dir.mkdir(parents=True, exist_ok=True)
        (dreamer_dir / "dreamer-cycle-15-20260624.md").write_text("# Dreamer evidence\n## Candidate 1: `test-slug` — GREEN")

        with patch.object(o, "kanban_check_task", return_value=("done", "")):
            with patch.object(o, "acquire_lock", return_value=True):
                with patch.object(o, "release_lock"):
                    with patch.object(o, "reconcile_state"):
                        with patch.object(o, "safety_checks", return_value={
                            "main_green": True, "open_prs": True,
                            "active_builders": True, "no_revert_policy": True,
                            "no_revert_missing_profiles": []
                        }):
                            with patch.object(v16, "STATE_FILE", state_path):
                                with patch.object(v16, "EVIDENCE_DIR", evidence_dir):
                                    o.run()

        # Mode blocks BUILDER → should NOT be BUILDER
        assert o.state["phase"] != "BUILDER"
        assert "MODE_VIOLATION" in o.state["status"] or "STOPPED" in o.state["phase"]


class TestResearcherCompletionGuard:
    """Test that RESEARCHER completion with stop_after_phase=RESEARCHER halts."""

    def test_stop_after_researcher(self, tmp_path):
        """Test 6: stop_after_phase=RESEARCHER stops after Researcher."""
        o, state_path, evidence_dir = make_orchestrator(
            tmp_path,
            {"mode": "RESEARCHER_DREAMER_ONLY", "stop_after_phase": "RESEARCHER",
             "phase": "RESEARCHER", "status": "WAITING"}
        )
        researcher_dir = evidence_dir / "researcher"
        researcher_dir.mkdir(parents=True, exist_ok=True)
        (researcher_dir / "researcher-cycle-15-20260624.md").write_text("# Researcher evidence\n- Finding 1")

        with patch.object(o, "kanban_check_task", return_value=("done", "")):
            with patch.object(o, "acquire_lock", return_value=True):
                with patch.object(o, "release_lock"):
                    with patch.object(o, "reconcile_state"):
                        with patch.object(o, "safety_checks", return_value={
                            "main_green": True, "open_prs": True,
                            "active_builders": True, "no_revert_policy": True,
                            "no_revert_missing_profiles": []
                        }):
                            with patch.object(v16, "STATE_FILE", state_path):
                                with patch.object(v16, "EVIDENCE_DIR", evidence_dir):
                                    o.run()

        assert o.state["phase"] == "STOPPED_AFTER_RESEARCHER"
        assert o.state["status"] == "PROOF_COMPLETE"


class TestStoppedStateIdempotent:
    """Test that STOPPED_AFTER_* state does nothing on subsequent runs."""

    def test_stopped_after_dreamer_noop(self, tmp_path):
        """Test 7: next run at STOPPED_AFTER_DREAMER starts nothing."""
        o, state_path, evidence_dir = make_orchestrator(
            tmp_path,
            {"phase": "STOPPED_AFTER_DREAMER", "status": "PROOF_COMPLETE",
             "stop_after_phase": "DREAMER"}
        )
        builder_called = False
        original_phase_builder = o.phase_builder

        def spy_builder(*args, **kwargs):
            nonlocal builder_called
            builder_called = True
            return original_phase_builder(*args, **kwargs)

        with patch.object(o, "phase_builder", side_effect=spy_builder):
            with patch.object(o, "acquire_lock", return_value=True):
                with patch.object(o, "release_lock"):
                    with patch.object(o, "reconcile_state"):
                        with patch.object(v16, "STATE_FILE", state_path):
                            with patch.object(v16, "EVIDENCE_DIR", evidence_dir):
                                o.run()

        assert builder_called is False
        # State unchanged
        assert o.state["phase"] == "STOPPED_AFTER_DREAMER"
        assert o.state["status"] == "PROOF_COMPLETE"


class TestPROrchestrationBlocked:
    """Test that PR creation is blocked in restricted mode."""

    def test_pr_create_blocked_in_restricted_mode(self, tmp_path):
        """Test 4: mode=RESEARCHER_DREAMER_ONLY blocks PR creation."""
        o, state_path, _ = make_orchestrator(
            tmp_path,
            {"mode": "RESEARCHER_DREAMER_ONLY"}
        )
        with patch.object(v16, "STATE_FILE", state_path):
            pr_url, err = o.orchestrator_push_and_create_pr("some-candidate", 15)
        assert pr_url is None
        assert err == "BLOCKED_MODE_VIOLATION"
        assert o.state["status"] == "BLOCKED_MODE_VIOLATION"


class TestMergeBlocked:
    """Test that merge is blocked in restricted mode."""

    def test_merge_blocked_in_restricted_mode(self, tmp_path):
        """Test 8: mode=RESEARCHER_DREAMER_ONLY blocks Merge."""
        o, state_path, _ = make_orchestrator(
            tmp_path,
            {"mode": "RESEARCHER_DREAMER_ONLY", "pr_open": "https://github.com/test/repo/pull/1"}
        )
        with patch.object(v16, "STATE_FILE", state_path):
            result = o.phase_merge(15, "https://github.com/test/repo/pull/1")
        assert result is False
        assert o.state["status"] == "BLOCKED_MODE_VIOLATION"


class TestBuilderEntryBlocked:
    """Test that entering BUILDER phase in restricted mode is blocked."""

    def test_builder_phase_blocked_in_run(self, tmp_path):
        """Test 2: BUILDER phase entry blocked by mode."""
        o, state_path, evidence_dir = make_orchestrator(
            tmp_path,
            {"mode": "RESEARCHER_DREAMER_ONLY",
             "phase": "BUILDER", "status": "NEXT_PHASE"}
        )
        builder_dispatched = False

        with patch.object(o, "phase_builder", return_value=True) as mock_b:
            with patch.object(o, "acquire_lock", return_value=True):
                with patch.object(o, "release_lock"):
                    with patch.object(o, "reconcile_state"):
                        with patch.object(o, "safety_checks", return_value={
                            "main_green": True, "open_prs": True,
                            "active_builders": True, "no_revert_policy": True,
                            "no_revert_missing_profiles": []
                        }):
                            with patch.object(v16, "STATE_FILE", state_path):
                                with patch.object(v16, "EVIDENCE_DIR", evidence_dir):
                                    o.run()

        # phase_builder should NOT have been called
        assert not mock_b.called
        assert o.state["status"] == "BLOCKED_MODE_VIOLATION"
