"""PR Orchestration Tests v0.15

Testet: auto push, auto PR create, conflict detection,
       merge gate, test baseline, no admin merge.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path.home() / ".hermes/scripts"))
import peekxd_buildroom_loop_v15 as v15
from peekxd_buildroom_loop_v15 import BuildroomOrchestrator


class TestPROrchestration:
    """Test orchestrator_push_and_create_pr."""

    def setup_method(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmpdir.name) / "orchestrator-state.json"
        self._state_patcher = patch.object(v15, "STATE_FILE", self.state_path)
        self._state_patcher.start()
        self.o = BuildroomOrchestrator()
        self.o.state["cycle"] = 14
        self.o.state["current_candidate"] = "test-candidate"

    def teardown_method(self):
        self._state_patcher.stop()
        self.tmpdir.cleanup()

    def test_push_and_create_pr_success(self):
        with patch.object(self.o, "find_builder_branch", return_value="autonomy/peekxd/test-candidate-20260101"):
            with patch.object(self.o, "check_main_green", return_value=True):
                with patch.object(self.o, "run_cmd") as mock_run:
                    # Push succeeds
                    mock_run.side_effect = [
                        (True, "", ""),  # git push
                        (True, "https://github.com/WietRob/peekxd/pull/99", ""),  # gh pr create
                    ]
                    pr_url, err = self.o.orchestrator_push_and_create_pr("test-candidate", 14)
        assert pr_url == "https://github.com/WietRob/peekxd/pull/99"
        assert err == "OK"
        assert self.o.state["pr_open"] == pr_url
        assert self.o.state["phase"] == "REVIEWER"
        assert self.o.state["status"] == "NEXT_PHASE"

    def test_no_branch_blocks(self):
        with patch.object(self.o, "find_builder_branch", return_value=None):
            pr_url, err = self.o.orchestrator_push_and_create_pr("test-candidate", 14)
        assert pr_url is None
        assert err == "BLOCKED_NO_BRANCH"
        assert "BLOCKED" in self.o.state["status"]

    def test_dirty_tree_blocks(self):
        with patch.object(self.o, "find_builder_branch", return_value="autonomy/peekxd/test-candidate"):
            with patch.object(self.o, "check_main_green", return_value=False):
                pr_url, err = self.o.orchestrator_push_and_create_pr("test-candidate", 14)
        assert pr_url is None
        assert err == "BLOCKED_DIRTY_TREE"

    def test_push_fail_blocks(self):
        with patch.object(self.o, "find_builder_branch", return_value="autonomy/peekxd/test-candidate"):
            with patch.object(self.o, "check_main_green", return_value=True):
                with patch.object(self.o, "run_cmd") as mock_run:
                    mock_run.return_value = (False, "", "Permission denied")
                    pr_url, err = self.o.orchestrator_push_and_create_pr("test-candidate", 14)
        assert pr_url is None
        assert "BLOCKED" in err

    def test_pr_create_fail_blocks(self):
        with patch.object(self.o, "find_builder_branch", return_value="autonomy/peekxd/test-candidate"):
            with patch.object(self.o, "check_main_green", return_value=True):
                with patch.object(self.o, "run_cmd") as mock_run:
                    mock_run.side_effect = [
                        (True, "", ""),  # push ok
                        (False, "", "already exists"),  # pr create fail
                    ]
                    pr_url, err = self.o.orchestrator_push_and_create_pr("test-candidate", 14)
        assert pr_url is None
        assert err == "BLOCKED_PR_CREATE_FAILED"


class TestConflictDetection:
    """Test detect_merge_conflict."""

    def setup_method(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmpdir.name) / "orchestrator-state.json"
        self._state_patcher = patch.object(v15, "STATE_FILE", self.state_path)
        self._state_patcher.start()
        self.o = BuildroomOrchestrator()

    def teardown_method(self):
        self._state_patcher.stop()
        self.tmpdir.cleanup()

    def test_mergeable(self):
        json_out = json.dumps({"mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"})
        with patch.object(self.o, "run_cmd", return_value=(True, json_out, "")):
            status, reason = self.o.detect_merge_conflict("https://github.com/fake/pr/1")
        assert status == "MERGEABLE"

    def test_conflict(self):
        json_out = json.dumps({"mergeable": "CONFLICTING", "mergeStateStatus": "BLOCKED"})
        with patch.object(self.o, "run_cmd", return_value=(True, json_out, "")):
            status, reason = self.o.detect_merge_conflict("https://github.com/fake/pr/1")
        assert status == "CONFLICT"

    def test_gh_auth_blocked(self):
        with patch.object(self.o, "run_cmd", return_value=(False, "", "HTTP 403 auth")):
            status, reason = self.o.detect_merge_conflict("https://github.com/fake/pr/1")
        assert status == "GH_AUTH_BLOCKED"

    def test_unknown(self):
        json_out = json.dumps({"mergeable": "UNKNOWN", "mergeStateStatus": "UNKNOWN"})
        with patch.object(self.o, "run_cmd", return_value=(True, json_out, "")):
            status, reason = self.o.detect_merge_conflict("https://github.com/fake/pr/1")
        assert status == "UNKNOWN"


class TestMergeGate:
    """Test merge gate enforces all rules."""

    def setup_method(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmpdir.name) / "orchestrator-state.json"
        self._state_patcher = patch.object(v15, "STATE_FILE", self.state_path)
        self._state_patcher.start()
        self.o = BuildroomOrchestrator()
        self.o.state["cycle"] = 14

    def teardown_method(self):
        self._state_patcher.stop()
        self.tmpdir.cleanup()

    def test_no_approve_blocks(self):
        with patch.object(self.o, "check_any_evidence", return_value=(True, Path("/fake/reviewer.md"))):
            with patch.object(Path, "read_text", return_value="HOLD_FOR_BOSS: needs human review"):
                result = self.o.phase_merge(14, "https://github.com/fake/pr/1")
        assert result == False
        assert "BLOCKED" in self.o.state.get("status", "")

    def test_approve_but_conflict_blocks(self):
        with patch.object(self.o, "check_any_evidence", return_value=(True, Path("/fake/reviewer.md"))):
            with patch.object(Path, "read_text", return_value="APPROVE_MERGE: looks good"):
                with patch.object(self.o, "detect_merge_conflict", return_value=("CONFLICT", "status=BLOCKED")):
                    result = self.o.phase_merge(14, "https://github.com/fake/pr/1")
        assert result == False
        assert "CONFLICT" in self.o.state.get("status", "")

    def test_no_reviewer_evidence_blocks(self):
        with patch.object(self.o, "check_any_evidence", return_value=(False, None)):
            result = self.o.phase_merge(14, "https://github.com/fake/pr/1")
        assert result == False


class TestBaseline:
    """Test verify_test_baseline."""

    def setup_method(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmpdir.name) / "orchestrator-state.json"
        self.bl_path = Path(self.tmpdir.name) / "test-baseline.json"
        self._state_patcher = patch.object(v15, "STATE_FILE", self.state_path)
        self._baseline_patcher = patch.object(v15, "BASELINE_FILE", self.bl_path)
        self._state_patcher.start()
        self._baseline_patcher.start()
        self.o = BuildroomOrchestrator()

    def teardown_method(self):
        self._baseline_patcher.stop()
        self._state_patcher.stop()
        self.tmpdir.cleanup()

    def test_baseline_records_failures(self):
        stdout = "FAILED tests/test_selftest.py::test_selftest_unit\nFAILED tests/test_selftest.py::test_selftest_module\n493 passed, 3 failed"
        with patch.object(self.o, "run_cmd") as mock_run:
            mock_run.side_effect = [
                (True, "", ""),  # git checkout
                (True, "", ""),  # git pull
                (False, stdout, ""),  # pytest (failing)
            ]
            baseline = self.o.verify_test_baseline()
        assert baseline["all_passed"] == False
        assert "test_selftest_unit" in str(baseline.get("pre_existing_failures", []))
        assert baseline["total_passed"] == 493

    def test_baseline_all_green(self):
        with patch.object(self.o, "run_cmd") as mock_run:
            mock_run.side_effect = [
                (True, "", ""),
                (True, "", ""),
                (True, "496 passed in 8.06s", ""),
            ]
            baseline = self.o.verify_test_baseline()
        assert baseline["all_passed"] == True
