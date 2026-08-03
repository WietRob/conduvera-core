import pytest
import sys
import json
import time
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call

sys.path.insert(0, str(Path.home() / ".hermes/scripts"))
import peekxd_buildroom_loop_v13 as v13
from peekxd_buildroom_loop_v13 import BuildroomOrchestrator, EVIDENCE_DIR, VALID_SLUG_RE, FORBIDDEN_SLUGS


class TestEvidenceContractIntegration:
    """Integration tests for Evidence Contract enforcement."""

    def setup_method(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._state_patcher = patch.object(v13, 'STATE_FILE', Path(self._tmpdir.name) / 'orchestrator-state.json')
        self._state_patcher.start()
        self.o = BuildroomOrchestrator()

    def teardown_method(self):
        self._state_patcher.stop()
        self._tmpdir.cleanup()

    def test_01_missing_researcher_evidence_blocks_dreamer(self, tmp_path):
        """Test 1: Missing Researcher Evidence blocks DREAMER."""
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            # No researcher evidence
            exists, path = self.o.check_any_evidence("RESEARCHER", 14)
            assert exists is False
            # Dreamer should be blocked
            result = self.o.phase_dreamer(14)
            assert result is False

    def test_02_valid_researcher_evidence_allows_dreamer(self, tmp_path):
        """Test 2: Valid Researcher Evidence allows DREAMER."""
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            # Create researcher evidence
            evidence = tmp_path / "researcher" / "researcher-cycle-14-20260622.md"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("# Researcher Report\n\n## Gap 1\n- Candidate: test-feature")

            # Mock kanban_create to avoid actual task creation
            with patch.object(self.o, 'kanban_create', return_value=("t_test_01", "OK")):
                with patch.object(self.o, 'kanban_show', return_value=(True, "")):
                    with patch.object(self.o, 'kanban_dispatch', return_value=(True, "")):
                        with patch.object(self.o, 'kanban_check_task', return_value=("running", "")):
                            result = self.o.phase_dreamer(14)
                            assert result is True

    def test_03_missing_dreamer_evidence_blocks_builder(self, tmp_path):
        """Test 3: Missing Dreamer Evidence blocks BUILDER."""
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            # No dreamer evidence
            exists, path = self.o.check_any_evidence("DREAMER", 14)
            assert exists is False
            # Builder should be blocked
            result = self.o.phase_builder(14)
            assert result is False

    def test_04_dreamer_evidence_with_yellow_blocks_builder(self, tmp_path):
        """Test 4: Dreamer Evidence with yellow blocks BUILDER."""
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            # Create dreamer evidence with yellow (forbidden)
            evidence = tmp_path / "dreamer" / "dreamer-cycle-14-20260622.md"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("""
# Dreamer Report

### Candidate: yellow
- Risk: GREEN
- Title: Yellow candidate
""")

            # Builder should be blocked because yellow is forbidden
            result = self.o.phase_builder(14)
            assert result is False

    def test_05_valid_dreamer_evidence_allows_builder(self, tmp_path):
        """Test 5: Valid Dreamer Evidence with GREEN slug allows BUILDER."""
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            # Create dreamer evidence with valid GREEN candidate
            evidence = tmp_path / "dreamer" / "dreamer-cycle-14-20260622.md"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("""
# Dreamer Report

### Candidate: semantic-snapshot-diff
- Risk: GREEN
- Title: Add semantic snapshot diff support
""")

            # Mock kanban_create to avoid actual task creation
            with patch.object(self.o, 'kanban_create', return_value=("t_test_05", "OK")):
                with patch.object(self.o, 'kanban_show', return_value=(True, "")):
                    with patch.object(self.o, 'kanban_dispatch', return_value=(True, "")):
                        with patch.object(self.o, 'kanban_check_task', return_value=("running", "")):
                            result = self.o.phase_builder(14)
                            assert result is True
                            assert self.o.state.get("current_candidate") == "semantic-snapshot-diff"

    def test_06_missing_builder_evidence_blocks_reviewer(self, tmp_path):
        """Test 6: Missing Builder Evidence blocks REVIEWER."""
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            # Set current candidate
            self.o.state["current_candidate"] = "semantic-snapshot-diff"
            # No builder evidence
            exists, path = self.o.check_any_evidence("BUILDER", 14, "semantic-snapshot-diff")
            assert exists is False
            # Reviewer should be blocked
            result = self.o.phase_reviewer(14, "https://github.com/test/pr/1")
            assert result is False

    def test_07_missing_reviewer_evidence_blocks_merge(self, tmp_path):
        """Test 7: Missing Reviewer Evidence blocks MERGE."""
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            # No reviewer evidence
            exists, path = self.o.check_any_evidence("REVIEWER", 14)
            assert exists is False
            # Merge should be blocked
            result = self.o.phase_merge(14, "https://github.com/test/pr/1")
            assert result is False

    def test_08_reviewer_verdict_hold_blocks_merge(self, tmp_path):
        """Test 8: Reviewer Verdict HOLD_FOR_BOSS blocks MERGE."""
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            # Create reviewer evidence with HOLD_FOR_BOSS
            evidence = tmp_path / "reviewer" / "reviewer-cycle-14-20260622.md"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("""
# Reviewer Report

## Verdict: HOLD_FOR_BOSS

### Reason
Requires human review.
""")

            # Merge should be blocked
            result = self.o.phase_merge(14, "https://github.com/test/pr/1")
            assert result is False

    def test_09_reviewer_verdict_approve_allows_merge(self, tmp_path):
        """Test 9: Reviewer Verdict APPROVE_MERGE allows MERGE."""
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            # Create reviewer evidence with APPROVE_MERGE
            evidence = tmp_path / "reviewer" / "reviewer-cycle-14-20260622.md"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("""
# Reviewer Report

## Verdict: APPROVE_MERGE

### Scope
- src/diff.py

### Tests
- 5/5 passed

### Safety
- No secrets found
""")

            # Mock gh pr merge to avoid actual merge
            with patch.object(self.o, 'run_cmd', return_value=(True, "Merged", "")):
                result = self.o.phase_merge(14, "https://github.com/test/pr/1")
                assert result is True


class TestLockRecoveryIntegration:
    """Integration tests for Lock Recovery without manual rm."""

    def setup_method(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._state_patcher = patch.object(v13, 'STATE_FILE', Path(self._tmpdir.name) / 'orchestrator-state.json')
        self._state_patcher.start()
        self.o = BuildroomOrchestrator()

    def teardown_method(self):
        self._state_patcher.stop()
        self._tmpdir.cleanup()

    def test_10_lock_without_evidence_not_deleted(self, tmp_path):
        """Test 10: Lock without Evidence is NOT blindly deleted."""
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            # Create old lock file
            lock = tmp_path / ".researcher-running"
            lock.write_text("old")
            old_time = time.time() - 10000
            os.utime(lock, (old_time, old_time))

            # No evidence, task running
            with patch.object(self.o, 'check_any_evidence', return_value=(False, None)):
                with patch.object(self.o, 'kanban_check_task', return_value=("running", "")):
                    recovered, reason = self.o.recover_phase_lock("RESEARCHER", 14)
                    assert recovered is False
                    assert reason == "LOCK_STALE_NO_EVIDENCE"
                    assert lock.exists()  # Lock still exists

    def test_11_lock_with_evidence_auto_recovered(self, tmp_path):
        """Test 11: Lock with Evidence is automatically recovered."""
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            # Create old lock file
            lock = tmp_path / ".researcher-running"
            lock.write_text("old")
            old_time = time.time() - 10000
            os.utime(lock, (old_time, old_time))

            # Create evidence
            evidence = tmp_path / "researcher" / "researcher-cycle-14-20260622.md"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("# Researcher Report")

            with patch.object(self.o, 'check_any_evidence', return_value=(True, evidence)):
                recovered, reason = self.o.recover_phase_lock("RESEARCHER", 14)
                assert recovered is True
                assert reason == "evidence_found"
                assert not lock.exists()  # Lock removed


class TestTaskVisibilityIntegration:
    """Integration tests for Task Visibility Guard."""

    def setup_method(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._state_patcher = patch.object(v13, 'STATE_FILE', Path(self._tmpdir.name) / 'orchestrator-state.json')
        self._state_patcher.start()
        self.o = BuildroomOrchestrator()

    def teardown_method(self):
        self._state_patcher.stop()
        self._tmpdir.cleanup()

    def test_12_task_not_visible_blocked(self, tmp_path):
        """Test 12: Task created but not visible => BLOCKED."""
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            # Mock kanban_create to return task ID
            with patch.object(self.o, 'kanban_create', return_value=("t_test_12", "OK")):
                # Mock kanban_show to fail (task not visible)
                with patch.object(self.o, 'kanban_show', return_value=(False, "")):
                    result, err = self.o.create_task_with_verify(
                        "Test Task", "researcher", "Test body", "RESEARCHER"
                    )
                    assert result is None
                    assert "TASK_NOT_VISIBLE" in err


class TestBlockedRuntimeFix:
    """Test that BLOCKED_RUNTIME_FIX prevents Cycle 14 start."""

    def setup_method(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._state_patcher = patch.object(v13, 'STATE_FILE', Path(self._tmpdir.name) / 'orchestrator-state.json')
        self._state_patcher.start()
        self.o = BuildroomOrchestrator()

    def teardown_method(self):
        self._state_patcher.stop()
        self._tmpdir.cleanup()

    def test_blocked_runtime_fix_prevents_start(self, tmp_path):
        """Test: BLOCKED_RUNTIME_FIX state prevents any phase execution."""
        state_path = tmp_path / "orchestrator-state.json"
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path), \
             patch.object(v13, 'STATE_FILE', state_path):
            # Set state to BLOCKED_RUNTIME_FIX
            self.o.state['cycle'] = 14
            self.o.state['phase'] = 'BLOCKED_RUNTIME_FIX'
            self.o.state['status'] = 'CYCLE_13_NOT_AUTONOMOUS'
            self.o.save_state()

            # Mock all phase methods to track if they're called
            with patch.object(self.o, 'phase_researcher') as mock_researcher:
                with patch.object(self.o, 'phase_dreamer') as mock_dreamer:
                    with patch.object(self.o, 'phase_builder') as mock_builder:
                        with patch.object(self.o, 'phase_reviewer') as mock_reviewer:
                            with patch.object(self.o, 'phase_merge') as mock_merge:
                                with patch.object(self.o, 'phase_reporter') as mock_reporter:
                                    # Run orchestrator
                                    self.o.run()

                                    # Verify no phase methods were called
                                    mock_researcher.assert_not_called()
                                    mock_dreamer.assert_not_called()
                                    mock_builder.assert_not_called()
                                    mock_reviewer.assert_not_called()
                                    mock_merge.assert_not_called()
                                    mock_reporter.assert_not_called()


class TestOpenPRsGate:
    """Test open_prs safety gate logic."""

    def setup_method(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._state_patcher = patch.object(v13, 'STATE_FILE', Path(self._tmpdir.name) / 'orchestrator-state.json')
        self._state_patcher.start()
        self.o = BuildroomOrchestrator()

    def teardown_method(self):
        self._state_patcher.stop()
        self._tmpdir.cleanup()

    def test_zero_open_prs_allows_builder(self):
        """Test: 0 open PRs allows Builder."""
        with patch.object(self.o, 'check_open_prs', return_value=(0, [])):
            self.o.state['phase'] = 'BUILDER'
            safety = self.o.safety_checks()
            assert safety['open_prs'] is True

    def test_one_open_pr_reviewer_phase_allows(self):
        """Test: 1 open PR with REVIEWER phase allows."""
        with patch.object(self.o, 'check_open_prs', return_value=(1, [{"number": 17, "url": "https://github.com/test/pr/17"}])):
            self.o.state['phase'] = 'REVIEWER'
            self.o.state['pr_open'] = "https://github.com/test/pr/17"
            safety = self.o.safety_checks()
            assert safety['open_prs'] is True

    def test_one_open_pr_merge_phase_allows(self):
        """Test: 1 open PR with MERGE phase allows."""
        with patch.object(self.o, 'check_open_prs', return_value=(1, [{"number": 17, "url": "https://github.com/test/pr/17"}])):
            self.o.state['phase'] = 'MERGE'
            safety = self.o.safety_checks()
            assert safety['open_prs'] is True

    def test_multiple_open_prs_blocks(self):
        """Test: Multiple open PRs blocks."""
        with patch.object(self.o, 'check_open_prs', return_value=(2, [{"number": 17}, {"number": 18}])):
            self.o.state['phase'] = 'BUILDER'
            safety = self.o.safety_checks()
            assert safety['open_prs'] is False

    def test_one_open_pr_builder_phase_blocks(self):
        """Test: 1 open PR with BUILDER phase blocks."""
        with patch.object(self.o, 'check_open_prs', return_value=(1, [{"number": 17, "url": "https://github.com/test/pr/17"}])):
            self.o.state['phase'] = 'BUILDER'
            safety = self.o.safety_checks()
            assert safety['open_prs'] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
