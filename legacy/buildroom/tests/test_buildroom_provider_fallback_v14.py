"""Provider Fallback Tests v0.14

Testet: classify_task_failure, select_fallback_profile, attempt tracking,
       retry without evidence, max attempts, no phase transition without evidence.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path.home() / ".hermes/scripts"))
import peekxd_buildroom_loop_v14 as v14
from peekxd_buildroom_loop_v14 import (
    BuildroomOrchestrator, PROVIDER_QUOTA_PATTERNS, PROVIDER_AUTH_PATTERNS,
    MAX_ATTEMPTS_PER_PHASE, FALLBACK_POLICY,
)


class TestFailureClassifier:
    """Test classify_task_failure correctly identifies root causes."""

    def setup_method(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmpdir.name) / "orchestrator-state.json"
        self._state_patcher = patch.object(v14, "STATE_FILE", self.state_path)
        self._state_patcher.start()
        self.o = BuildroomOrchestrator()

    def teardown_method(self):
        self._state_patcher.stop()
        self.tmpdir.cleanup()

    def test_classify_provider_quota_403(self):
        log = "HTTP 403: You've reached your usage limit for this billing cycle. Provider: kimi-coding"
        with patch.object(self.o, "kanban_get_task_log", return_value=log):
            fc, reason = self.o.classify_task_failure("RESEARCHER", "t_test")
        assert fc == "PROVIDER_QUOTA"
        assert "quota" in reason.lower() or "billing" in reason.lower()

    def test_classify_provider_quota_rate_limit(self):
        log = "HTTP 429 rate limit exceeded Provider: deepseek"
        with patch.object(self.o, "kanban_get_task_log", return_value=log):
            fc, reason = self.o.classify_task_failure("RESEARCHER", "t_test")
        assert fc == "PROVIDER_QUOTA"

    def test_classify_provider_auth_401(self):
        log = "HTTP 401 invalid API key"
        with patch.object(self.o, "kanban_get_task_log", return_value=log):
            fc, _ = self.o.classify_task_failure("RESEARCHER", "t_test")
        assert fc == "PROVIDER_AUTH"

    def test_classify_token_expired(self):
        log = "Error: token expired or incorrect Provider: zai"
        with patch.object(self.o, "kanban_get_task_log", return_value=log):
            fc, _ = self.o.classify_task_failure("RESEARCHER", "t_test")
        assert fc == "PROVIDER_AUTH"

    def test_classify_protocol_violation(self):
        log = "worker exited cleanly (rc=0) without calling kanban_complete or kanban_block — protocol violation"
        with patch.object(self.o, "kanban_get_task_log", return_value=log):
            fc, _ = self.o.classify_task_failure("RESEARCHER", "t_test")
        assert fc == "PROTOCOL_VIOLATION"

    def test_classify_unknown(self):
        log = "some random unrelated log message here"
        with patch.object(self.o, "kanban_get_task_log", return_value=log):
            fc, _ = self.o.classify_task_failure("RESEARCHER", "t_test")
        assert fc == "UNKNOWN"

    def test_classify_no_log(self):
        with patch.object(self.o, "kanban_get_task_log", return_value=""):
            fc, _ = self.o.classify_task_failure("RESEARCHER", "t_test")
        assert fc == "UNKNOWN"


class TestFallbackPolicy:
    """Test select_fallback_profile returns correct profiles."""

    def setup_method(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmpdir.name) / "orchestrator-state.json"
        self._state_patcher = patch.object(v14, "STATE_FILE", self.state_path)
        self._state_patcher.start()
        self.o = BuildroomOrchestrator()

    def teardown_method(self):
        self._state_patcher.stop()
        self.tmpdir.cleanup()

    def test_researcher_attempt_0_is_primary(self):
        profile, desc = self.o.select_fallback_profile("RESEARCHER", 0)
        assert profile == "researcher"

    def test_researcher_attempt_1_is_deepseek(self):
        profile, desc = self.o.select_fallback_profile("RESEARCHER", 1)
        assert profile == "researcher"

    def test_researcher_attempt_2_is_analyst(self):
        profile, desc = self.o.select_fallback_profile("RESEARCHER", 2)
        assert profile == "analyst"

    def test_researcher_attempt_3_is_deepseek_flash(self):
        profile, desc = self.o.select_fallback_profile("RESEARCHER", 3)
        assert profile == "researcher"

    def test_researcher_attempt_4_is_analyst_gpt55(self):
        profile, desc = self.o.select_fallback_profile("RESEARCHER", 4)
        assert profile == "analyst"

    def test_researcher_attempt_5_is_hold(self):
        profile, desc = self.o.select_fallback_profile("RESEARCHER", 5)
        assert profile is None

    def test_reviewer_attempt_0_is_codex_spark(self):
        profile, desc = self.o.select_fallback_profile("REVIEWER", 0)
        assert profile == "reviewer"

    def test_builder_attempt_0_is_builder_codex(self):
        profile, desc = self.o.select_fallback_profile("BUILDER", 0)
        assert profile == "builder"


class TestAttemptTracking:
    """Test attempt records are properly archived."""

    def setup_method(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmpdir.name) / "orchestrator-state.json"
        self._state_patcher = patch.object(v14, "STATE_FILE", self.state_path)
        self._state_patcher.start()
        self.o = BuildroomOrchestrator()
        # Init with a known state
        self.o.state["task_ids"] = {"RESEARCHER": "t_old_task"}
        self.o.state["attempts"] = {}

    def teardown_method(self):
        self._state_patcher.stop()
        self.tmpdir.cleanup()

    def test_attempt_archived_after_retry(self):
        with patch.object(self.o, "kanban_get_task_log", return_value="HTTP 403 quota exhausted"):
            with patch.object(self.o, "kanban_check_task", return_value=("done", "")):
                with patch.object(self.o, "kanban_create", return_value=("t_new_task", "OK")):
                    with patch.object(self.o, "kanban_show", return_value=(True, "")):
                        with patch.object(self.o, "kanban_dispatch", return_value=(True, "")):
                            ok, reason = self.o.maybe_retry_phase("RESEARCHER", 14)
        
        attempts = self.o.state.get("attempts", {}).get("RESEARCHER", [])
        assert len(attempts) >= 1
        old_attempt = [a for a in attempts if a["task_id"] == "t_old_task"]
        assert len(old_attempt) == 1
        assert old_attempt[0]["failure_class"] == "PROVIDER_QUOTA"
        assert old_attempt[0]["evidence"] == False

    def test_old_task_id_removed_after_retry(self):
        with patch.object(self.o, "kanban_get_task_log", return_value="HTTP 403 quota exhausted"):
            with patch.object(self.o, "kanban_check_task", return_value=("done", "")):
                with patch.object(self.o, "kanban_create", return_value=("t_new_task", "OK")):
                    with patch.object(self.o, "kanban_show", return_value=(True, "")):
                        with patch.object(self.o, "kanban_dispatch", return_value=(True, "")):
                            ok, reason = self.o.maybe_retry_phase("RESEARCHER", 14)
        # Old task_id should be removed from active task_ids
        assert "RESEARCHER" in self.o.state["task_ids"]
        assert self.o.state["task_ids"]["RESEARCHER"] != "t_old_task"


class TestMaxRetries:
    """Test max attempts enforcement."""

    def setup_method(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmpdir.name) / "orchestrator-state.json"
        self._state_patcher = patch.object(v14, "STATE_FILE", self.state_path)
        self._state_patcher.start()
        self.o = BuildroomOrchestrator()
        self.o.state["task_ids"] = {"RESEARCHER": "t_dead"}
        self.o.state["attempts"] = {
            "RESEARCHER": [
                {"task_id": "t1", "failure_class": "PROVIDER_QUOTA"},
                {"task_id": "t2", "failure_class": "PROVIDER_QUOTA"},
                {"task_id": "t3", "failure_class": "PROVIDER_QUOTA"},
            ]
        }

    def teardown_method(self):
        self._state_patcher.stop()
        self.tmpdir.cleanup()

    def test_max_retries_blocked(self):
        with patch.object(self.o, "kanban_get_task_log", return_value="HTTP 403 quota exhausted"):
            with patch.object(self.o, "kanban_check_task", return_value=("done", "")):
                ok, reason = self.o.maybe_retry_phase("RESEARCHER", 14)
        assert not ok
        assert "BLOCKED_MAX_RETRIES" in reason


class TestNoTransitionWithoutEvidence:
    """Test phase never transitions without evidence."""

    def setup_method(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmpdir.name) / "orchestrator-state.json"
        self._state_patcher = patch.object(v14, "STATE_FILE", self.state_path)
        self._state_patcher.start()
        self.o = BuildroomOrchestrator()

    def teardown_method(self):
        self._state_patcher.stop()
        self.tmpdir.cleanup()

    def test_no_dreamer_without_researcher_evidence(self):
        self.o.state["cycle"] = 14
        self.o.state["phase"] = "RESEARCHER"
        self.o.state["status"] = "WAITING"
        self.o.state["task_ids"] = {"RESEARCHER": "t_dead"}
        with patch.object(self.o, "kanban_check_task", return_value=("done", "")):
            with patch.object(self.o, "check_any_evidence", return_value=(False, None)):
                complete, reason = self.o.check_phase_complete("RESEARCHER", 14)
        assert not complete
        assert reason == "TASK_DONE_BUT_NO_EVIDENCE"

    def test_transition_only_with_evidence(self):
        self.o.state["cycle"] = 14
        self.o.state["phase"] = "RESEARCHER"
        self.o.state["task_ids"] = {"RESEARCHER": "t_test_done"}
        with patch.object(self.o, "kanban_check_task", return_value=("done", "")):
            with patch.object(self.o, "check_any_evidence", return_value=(True, Path("/fake/evidence.md"))):
                complete, reason = self.o.check_phase_complete("RESEARCHER", 14)
        assert complete
        assert reason == "TASK_DONE_AND_EVIDENCE"


class TestNonRetryableFailures:
    """Test that UNKNOWN / MISSING_EVIDENCE etc. don't trigger retry."""

    def setup_method(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmpdir.name) / "orchestrator-state.json"
        self._state_patcher = patch.object(v14, "STATE_FILE", self.state_path)
        self._state_patcher.start()
        self.o = BuildroomOrchestrator()
        self.o.state["task_ids"] = {"RESEARCHER": "t_unknown"}

    def teardown_method(self):
        self._state_patcher.stop()
        self.tmpdir.cleanup()

    def test_unknown_failure_no_retry(self):
        with patch.object(self.o, "kanban_get_task_log", return_value="some unrelated text"):
            with patch.object(self.o, "kanban_check_task", return_value=("done", "")):
                ok, reason = self.o.maybe_retry_phase("RESEARCHER", 14)
        assert not ok
        assert "non_retryable" in reason
