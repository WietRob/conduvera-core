import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, str(Path.home() / ".hermes/scripts"))
from peekxd_buildroom_loop_v13 import BuildroomOrchestrator


class TestCandidateParser:
    """Test candidate parsing and validation."""

    def setup_method(self):
        self.o = BuildroomOrchestrator()

    def test_valid_slug_simple(self):
        assert self.o.validate_candidate_slug("semantic-snapshot-diff") == (True, "valid")

    def test_valid_slug_complex(self):
        assert self.o.validate_candidate_slug("mcp-scroll-tool-missing") == (True, "valid")

    def test_valid_slug_single_hyphen(self):
        assert self.o.validate_candidate_slug("test-feature") == (True, "valid")

    def test_forbidden_slug_green(self):
        assert self.o.validate_candidate_slug("green") == (False, "forbidden slug: green")

    def test_forbidden_slug_yellow(self):
        assert self.o.validate_candidate_slug("yellow") == (False, "forbidden slug: yellow")

    def test_forbidden_slug_red(self):
        assert self.o.validate_candidate_slug("red") == (False, "forbidden slug: red")

    def test_forbidden_slug_hold(self):
        assert self.o.validate_candidate_slug("hold") == (False, "forbidden slug: hold")

    def test_forbidden_slug_reject(self):
        assert self.o.validate_candidate_slug("reject") == (False, "forbidden slug: reject")

    def test_forbidden_slug_candidate(self):
        assert self.o.validate_candidate_slug("candidate") == (False, "forbidden slug: candidate")

    def test_forbidden_slug_build(self):
        assert self.o.validate_candidate_slug("build") == (False, "forbidden slug: build")

    def test_invalid_slug_no_hyphen(self):
        assert self.o.validate_candidate_slug("feature") == (False, "invalid slug format: feature")

    def test_invalid_slug_uppercase(self):
        assert self.o.validate_candidate_slug("Feature-Name") == (False, "invalid slug format: Feature-Name")

    def test_invalid_slug_underscore(self):
        assert self.o.validate_candidate_slug("feature_name") == (False, "invalid slug format: feature_name")

    def test_invalid_slug_empty(self):
        assert self.o.validate_candidate_slug("") == (False, "empty slug")

    def test_invalid_slug_none(self):
        assert self.o.validate_candidate_slug(None) == (False, "empty slug")

    def test_parse_candidates_from_header_format(self, tmp_path):
        evidence = tmp_path / "dreamer-cycle-13-20260622.md"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("""
# Dreamer Report

### Candidate: semantic-snapshot-diff
- Risk: GREEN
- Title: Add semantic snapshot diff support

### Candidate: mcp-scroll-tool-missing
- Risk: YELLOW
- Title: Fix MCP scroll tool

### Candidate: test-feature
- Risk: GREEN
- Title: Test feature
""")

        with patch.object(self.o, 'check_any_evidence', return_value=(True, evidence)):
            candidates, status = self.o.parse_dreamer_candidates(13)

        assert status == "OK"
        assert len(candidates) == 2  # Only GREEN candidates
        assert candidates[0]["slug"] == "semantic-snapshot-diff"
        assert candidates[0]["risk"] == "GREEN"
        assert candidates[1]["slug"] == "test-feature"

    def test_parse_candidates_no_green(self, tmp_path):
        evidence = tmp_path / "dreamer-cycle-13-20260622.md"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("""
# Dreamer Report

### Candidate: some-feature
- Risk: YELLOW
- Title: Some feature

### Candidate: another-feature
- Risk: RED
- Title: Another feature
""")

        with patch.object(self.o, 'check_any_evidence', return_value=(True, evidence)):
            candidates, status = self.o.parse_dreamer_candidates(13)

        assert status == "NO_GREEN_CANDIDATE"
        assert len(candidates) == 0

    def test_parse_candidates_yellow_not_selected(self, tmp_path):
        evidence = tmp_path / "dreamer-cycle-13-20260622.md"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("""
# Dreamer Report

### Candidate: yellow
- Risk: GREEN
- Title: Yellow candidate
""")

        with patch.object(self.o, 'check_any_evidence', return_value=(True, evidence)):
            candidates, status = self.o.parse_dreamer_candidates(13)

        # yellow is forbidden, so it should not be in candidates even if marked GREEN
        assert status == "NO_GREEN_CANDIDATE"
        assert len(candidates) == 0

    def test_select_candidate_valid(self, tmp_path):
        evidence = tmp_path / "dreamer-cycle-13-20260622.md"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("""
# Dreamer Report

### Candidate: semantic-snapshot-diff
- Risk: GREEN
- Title: Add semantic snapshot diff support

### Candidate: mcp-scroll-tool-missing
- Risk: GREEN
- Title: Fix MCP scroll tool
""")

        with patch.object(self.o, 'check_any_evidence', return_value=(True, evidence)):
            slug, status = self.o.select_candidate(13)

        assert status == "OK"
        assert slug == "semantic-snapshot-diff"

    def test_select_candidate_no_green(self, tmp_path):
        evidence = tmp_path / "dreamer-cycle-13-20260622.md"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("""
# Dreamer Report

### Candidate: some-feature
- Risk: YELLOW
""")

        with patch.object(self.o, 'check_any_evidence', return_value=(True, evidence)):
            slug, status = self.o.select_candidate(13)

        assert status == "NO_GREEN_CANDIDATE"
        assert slug is None

    def test_select_candidate_no_evidence(self):
        with patch.object(self.o, 'check_any_evidence', return_value=(False, None)):
            slug, status = self.o.select_candidate(13)

        assert status == "NO_DREAMER_EVIDENCE"
        assert slug is None


class TestEvidenceContract:
    """Test evidence contract enforcement."""

    def setup_method(self):
        self.o = BuildroomOrchestrator()

    def test_check_evidence_exists(self, tmp_path):
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            from datetime import datetime, timezone
            date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
            evidence = tmp_path / "researcher" / f"researcher-cycle-13-{date_str}.md"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("# Researcher Report")

            exists, path = self.o.check_evidence("RESEARCHER", 13)
            assert exists is True

    def test_check_evidence_missing(self, tmp_path):
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            exists, path = self.o.check_evidence("RESEARCHER", 13)
            assert exists is False

    def test_check_any_evidence_exists(self, tmp_path):
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            evidence = tmp_path / "researcher" / "researcher-cycle-13-20260622.md"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("# Researcher Report")

            exists, path = self.o.check_any_evidence("RESEARCHER", 13)
            assert exists is True

    def test_check_any_evidence_missing(self, tmp_path):
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            exists, path = self.o.check_any_evidence("RESEARCHER", 13)
            assert exists is False


class TestStateTransitions:
    """Test state transition rules."""

    def setup_method(self):
        self.o = BuildroomOrchestrator()

    def test_researcher_to_dreamer_requires_evidence(self, tmp_path):
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            # No evidence
            exists, path = self.o.check_any_evidence("RESEARCHER", 13)
            assert exists is False

    def test_dreamer_to_builder_requires_green_candidate(self, tmp_path):
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            evidence = tmp_path / "dreamer" / "dreamer-cycle-13-20260622.md"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("""
# Dreamer Report

### Candidate: yellow
- Risk: GREEN
""")

            with patch.object(self.o, 'check_any_evidence', return_value=(True, evidence)):
                slug, status = self.o.select_candidate(13)
                assert status == "NO_GREEN_CANDIDATE"
                assert slug is None

    def test_builder_to_reviewer_requires_builder_evidence(self, tmp_path):
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            # No builder evidence
            exists, path = self.o.check_any_evidence("BUILDER", 13, "test-candidate")
            assert exists is False


class TestLockRecovery:
    """Test lock recovery without manual rm."""

    def setup_method(self):
        self.o = BuildroomOrchestrator()

    def test_lock_recovery_with_evidence(self, tmp_path):
        import time
        import os
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            lock = tmp_path / ".researcher-running"
            lock.write_text("old")

            # Make lock old
            old_time = time.time() - 10000
            os.utime(lock, (old_time, old_time))

            # Create evidence
            evidence = tmp_path / "researcher" / "researcher-cycle-13-20260622.md"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("# Researcher Report")

            with patch.object(self.o, 'check_any_evidence', return_value=(True, evidence)):
                recovered, reason = self.o.recover_phase_lock("RESEARCHER", 13)
                assert recovered is True
                assert reason == "evidence_found"
                assert not lock.exists()

    def test_lock_recovery_without_evidence(self, tmp_path):
        with patch('peekxd_buildroom_loop_v13.EVIDENCE_DIR', tmp_path):
            lock = tmp_path / ".researcher-running"
            lock.write_text("old")

            # Make lock old
            import os
            import time
            old_time = time.time() - 10000
            os.utime(lock, (old_time, old_time))

            with patch.object(self.o, 'check_any_evidence', return_value=(False, None)):
                with patch.object(self.o, 'kanban_check_task', return_value=("running", "")):
                    recovered, reason = self.o.recover_phase_lock("RESEARCHER", 13)
                    assert recovered is False
                    assert reason == "LOCK_STALE_NO_EVIDENCE"
                    assert lock.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
