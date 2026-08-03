"""v0.24.2 Merge Gate Truth Tests.

Testet die Merge-Gate-Härtung aus v0.24.2.
"""
import json, sys, tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path.home() / ".hermes/scripts"))
import peekxd_buildroom_loop_v20 as v20
from peekxd_buildroom_loop_v20 import BuildroomOrchestrator


def _setup(tmpdir):
    state_path = Path(tmpdir) / "orchestrator-state.json"
    patcher = patch.object(v20, "STATE_FILE", state_path)
    patcher.start()
    o = BuildroomOrchestrator()
    o.state["cycle"] = 34
    o.state["current_candidate"] = "test-candidate"
    o.state["pr_open"] = "https://github.com/test/pr/99"
    o.check_phase_complete = lambda *_args: (True, "PHASE_COMPLETE")
    o.bound_task_verdict = lambda *_args: "APPROVE_MERGE"
    return o, patcher


class TestMergeGateDirtyTree:

    def test_blocked_reviewer_with_stale_evidence_never_reaches_merge(self, tmp_path):
        o, patcher = _setup(tmp_path)
        o.check_phase_complete = lambda *_args: (False, "TASK_TERMINAL_FAILURE:blocked")
        o.run_cmd = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("merge commands must not run")
        )
        assert o.phase_merge(34, "https://github.com/test/pr/99") is False
        assert o.state["status"] == "BLOCKED_REVIEWER_GATE:TASK_TERMINAL_FAILURE:blocked"
        patcher.stop()

    def test_request_fix_verdict_never_reaches_merge(self, tmp_path):
        o, patcher = _setup(tmp_path)
        o.bound_task_verdict = lambda *_args: "REQUEST_FIX"
        o.run_cmd = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("merge commands must not run")
        )
        assert o.phase_merge(34, "https://github.com/test/pr/99") is False
        assert o.state["status"] == "BLOCKED_REVIEWER_VERDICT:REQUEST_FIX"
        patcher.stop()

    def test_dirty_test_files_block(self, tmp_path):
        o, patcher = _setup(tmp_path)
        # v0.26.2: Use real evidence file instead of global Path.read_text mock
        ev_file = Path(tmp_path) / "reviewer-evidence.md"
        ev_file.write_text("APPROVE_MERGE")
        with patch.object(o, "detect_merge_conflict", return_value=("MERGEABLE", "")):
            with patch.object(o, "run_cmd") as m:
                m.side_effect = [(True, "tests/test_x.py\n", "")]
                with patch.object(o, "check_any_evidence", return_value=(True, ev_file)):
                    result = o.phase_merge(34, "https://github.com/test/pr/99")
        assert result is False
        assert o.state["status"] == "BLOCKED_DIRTY_TREE"
        patcher.stop()

    def test_dirty_non_test_warns(self, tmp_path):
        o, patcher = _setup(tmp_path)
        with patch.object(o, "detect_merge_conflict", return_value=("MERGEABLE", "")):
            with patch.object(o, "run_cmd") as m:
                m.side_effect = [
                    (True, "README.md\n", ""),        # git diff
                    (True, "", ""),                  # gh pr checkout
                    (True, "", ""),                  # pytest green
                    (True, "", ""),                  # gh pr merge
                    (True, "", ""),                  # git checkout main
                    (True, "", ""),                  # git pull
                ]
                with patch.object(o, "check_any_evidence", return_value=(True, Path("/f"))):
                    with patch.object(Path, "read_text", return_value="APPROVE_MERGE"):
                        result = o.phase_merge(34, "https://github.com/test/pr/99")
        assert result is True
        patcher.stop()


class TestMergeGateBranchCheck:

    def test_checkout_pr_branch(self, tmp_path):
        o, patcher = _setup(tmp_path)
        with patch.object(o, "detect_merge_conflict", return_value=("MERGEABLE", "")):
            with patch.object(o, "run_cmd") as m:
                m.side_effect = [
                    (True, "", ""),                  # git status clean
                    (True, "", ""),                  # gh pr checkout 99
                    (True, "", ""),                  # pytest green
                    (True, "", ""),                  # gh pr merge
                    (True, "", ""),                  # git checkout main
                    (True, "", ""),                  # git pull
                ]
                with patch.object(o, "check_any_evidence", return_value=(True, Path("/f"))):
                    with patch.object(Path, "read_text", return_value="APPROVE_MERGE"):
                        result = o.phase_merge(34, "https://github.com/test/pr/99")
        assert result is True
        calls = [c[0][0] for c in m.call_args_list]
        assert any("gh pr checkout 99" in c for c in calls)
        patcher.stop()

    def test_cannot_checkout_blocks(self, tmp_path):
        o, patcher = _setup(tmp_path)
        with patch.object(o, "detect_merge_conflict", return_value=("MERGEABLE", "")):
            with patch.object(o, "run_cmd") as m:
                m.side_effect = [
                    (True, "", ""),                  # git status clean
                    (False, "", "fatal"),            # gh pr checkout fail
                ]
                result = o.phase_merge(34, "https://github.com/test/pr/99")
        assert result is False
        assert "BLOCKED" in o.state["status"]
        patcher.stop()


class TestMergeGateTestCommand:

    def test_uses_pytest_command(self, tmp_path):
        o, patcher = _setup(tmp_path)
        cmds = []
        def track(cmd, **kw):
            cmds.append(cmd)
            return (True, "", "")
        with patch.object(o, "detect_merge_conflict", return_value=("MERGEABLE", "")):
            with patch.object(o, "run_cmd", side_effect=track):
                with patch.object(o, "check_any_evidence", return_value=(True, Path("/f"))):
                    with patch.object(Path, "read_text", return_value="APPROVE_MERGE"):
                        o.phase_merge(34, "https://github.com/test/pr/99")
        assert any("pytest" in c for c in cmds)
        patcher.stop()


class TestMergeGateTestFailure:

    def test_pr_test_failure_no_baseline_blocks(self, tmp_path):
        o, patcher = _setup(tmp_path)
        with patch.object(o, "detect_merge_conflict", return_value=("MERGEABLE", "")):
            with patch.object(o, "run_cmd") as m:
                m.side_effect = [
                    (True, "", ""),                  # git status clean
                    (True, "", ""),                  # gh pr checkout
                    (False, "FAILED test_x\n2 failed", ""),  # pytest fail
                ]
                with patch.object(o, "baseline_file", Path(tmp_path / "nope.json")):
                    result = o.phase_merge(34, "https://github.com/test/pr/99")
        assert result is False
        assert "BLOCKED" in o.state["status"]
        patcher.stop()

    def test_pre_existing_only_allows(self, tmp_path):
        o, patcher = _setup(tmp_path)
        # v0.26.2: Use real evidence file instead of global Path.read_text mock
        # (global Path mock breaks BASELINE_FILE.read_text for JSON parsing)
        ev_file = Path(tmp_path) / "reviewer-evidence.md"
        ev_file.write_text("APPROVE_MERGE")
        bl = Path(tmp_path) / "test-baseline.json"
        bl.write_text(json.dumps({"pre_existing_failures": ["tests/test_old.py::test_flaky"], "total_passed": 509, "all_passed": False}))
        with patch.object(o, "detect_merge_conflict", return_value=("MERGEABLE", "")):
            with patch.object(o, "run_cmd") as m:
                m.side_effect = [
                    (True, "", ""),                  # git status
                    (True, "", ""),                  # gh pr checkout
                    (False, "FAILED tests/test_old.py::test_flaky\n1 failed", ""),  # pytest
                    (True, "", ""),                  # gh pr merge
                    (True, "", ""),                  # git checkout main
                    (True, "", ""),                  # git pull
                ]
                with patch.object(o, "baseline_file", bl):
                    with patch.object(o, "check_any_evidence", return_value=(True, ev_file)):
                        result = o.phase_merge(34, "https://github.com/test/pr/99")
        assert result is True
        patcher.stop()

    def test_new_failure_blocks(self, tmp_path):
        o, patcher = _setup(tmp_path)
        # v0.26.2: Use real evidence file — global Path.read_text mock breaks baseline JSON
        ev_file = Path(tmp_path) / "reviewer-evidence.md"
        ev_file.write_text("APPROVE_MERGE")
        bl = Path(tmp_path) / "test-baseline.json"
        bl.write_text(json.dumps({"pre_existing_failures": ["tests/test_old.py::test_flaky"], "total_passed": 509, "all_passed": False}))
        with patch.object(o, "detect_merge_conflict", return_value=("MERGEABLE", "")):
            with patch.object(o, "run_cmd") as m:
                m.side_effect = [
                    (True, "", ""),
                    (True, "", ""),
                    (False, "FAILED tests/test_old.py::test_flaky\nFAILED tests/test_new.py::test_feature\n2 failed", ""),
                ]
                with patch.object(o, "baseline_file", bl):
                    with patch.object(o, "check_any_evidence", return_value=(True, ev_file)):
                        result = o.phase_merge(34, "https://github.com/test/pr/99")
        assert result is False
        assert o.state["status"] == "BLOCKED_NEW_TEST_FAILURES"
        patcher.stop()

    def test_all_green_passes(self, tmp_path):
        o, patcher = _setup(tmp_path)
        with patch.object(o, "detect_merge_conflict", return_value=("MERGEABLE", "")):
            with patch.object(o, "run_cmd") as m:
                m.side_effect = [
                    (True, "", ""),                  # git status
                    (True, "", ""),                  # gh pr checkout
                    (True, "512 passed", ""),        # pytest green
                    (True, "", ""),                  # gh pr merge
                    (True, "", ""),                  # git checkout main
                    (True, "", ""),                  # git pull
                ]
                with patch.object(o, "check_any_evidence", return_value=(True, Path("/f"))):
                    with patch.object(Path, "read_text", return_value="APPROVE_MERGE"):
                        result = o.phase_merge(34, "https://github.com/test/pr/99")
        assert result is True
        assert o.state["status"] != "BLOCKED_TESTS_NOT_GREEN"
        patcher.stop()
