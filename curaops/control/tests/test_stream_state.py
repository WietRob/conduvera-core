"""
Tests for Stream State Store and Worktree Safety Sentinel.
"""
import json
import tempfile
from pathlib import Path

import pytest

from curaops.control.stream_state import (
    StreamState, AgentReply, StreamStateStore, StreamRecord,
    InvalidTransitionError, InvalidReplyError, STATE_REPLY_MATRIX, TRANSITIONS,
)


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def store(tmp_dir):
    return StreamStateStore(control_dir=tmp_dir / "state")


def _make_registry_dir(tmp_dir, agent_id="joker", worktree="/tmp/test-wt"):
    """Create minimal registry for worktree sentinel tests."""
    from curaops.control.registry import AgentRegistry, AgentRecord, AgentStatus
    reg_dir = tmp_dir / "control"
    reg_dir.mkdir(parents=True, exist_ok=True)
    reg = AgentRegistry(control_dir=reg_dir)
    reg.register(AgentRecord(
        agent_id=agent_id, tool="manual", worktree=worktree,
        task="TASK-001", issue=1,
        gate_profile="default", status=AgentStatus.ACTIVE,
    ))
    return reg_dir


# ── StreamStateStore Tests ────────────────────────────────────

class TestStreamStateStore:

    def test_default_state_is_new(self, store):
        record = store.get("new-agent")
        assert record.state == StreamState.NEW
        assert record.agent == "new-agent"

    def test_set_state_new_to_assigned(self, store):
        record = store.set_state("agent1", StreamState.ASSIGNED, reason="Task assigned")
        assert record.state == StreamState.ASSIGNED

    def test_set_state_assigned_to_working(self, store):
        store.set_state("agent1", StreamState.ASSIGNED)
        record = store.set_state("agent1", StreamState.WORKING, reason="Agent started")
        assert record.state == StreamState.WORKING

    def test_set_state_working_to_ready_candidate(self, store):
        store.set_state("agent1", StreamState.ASSIGNED)
        store.set_state("agent1", StreamState.WORKING)
        record = store.set_state("agent1", StreamState.READY_CANDIDATE)
        assert record.state == StreamState.READY_CANDIDATE

    def test_set_state_ready_candidate_to_ready_for_review_requires_head_sha(self, store):
        store.set_state("agent1", StreamState.ASSIGNED)
        store.set_state("agent1", StreamState.WORKING)
        store.set_state("agent1", StreamState.READY_CANDIDATE)
        with pytest.raises(InvalidTransitionError, match="head_sha"):
            store.set_state("agent1", StreamState.READY_FOR_REVIEW)

    def test_set_state_ready_for_review_with_head_sha(self, store):
        store.set_state("agent1", StreamState.ASSIGNED)
        store.set_state("agent1", StreamState.WORKING)
        store.set_state("agent1", StreamState.READY_CANDIDATE)
        record = store.set_state("agent1", StreamState.READY_FOR_REVIEW, head_sha="abc123")
        assert record.state == StreamState.READY_FOR_REVIEW
        assert record.head_sha == "abc123"

    def test_working_to_blocked(self, store):
        store.set_state("agent1", StreamState.ASSIGNED)
        store.set_state("agent1", StreamState.WORKING)
        record = store.set_state("agent1", StreamState.BLOCKED_LOCAL_QUALITY_GATE, reason="Tests failed")
        assert record.state == StreamState.BLOCKED_LOCAL_QUALITY_GATE

    def test_invalid_transition_raises(self, store):
        with pytest.raises(InvalidTransitionError):
            store.set_state("agent1", StreamState.MERGED)  # NEW -> MERGED is invalid

    def test_validate_reply_blocked_only_blocker(self, store):
        store.set_state("agent1", StreamState.ASSIGNED)
        store.set_state("agent1", StreamState.WORKING)
        store.set_state("agent1", StreamState.BLOCKED_LOCAL_QUALITY_GATE)
        assert store.validate_reply("agent1", AgentReply.BLOCKER) is True
        assert store.validate_reply("agent1", AgentReply.ACK) is False
        assert store.validate_reply("agent1", AgentReply.PROGRESS) is False

    def test_validate_reply_working_allows_ack_progress(self, store):
        store.set_state("agent1", StreamState.ASSIGNED)
        store.set_state("agent1", StreamState.WORKING)
        assert store.validate_reply("agent1", AgentReply.ACK) is True
        assert store.validate_reply("agent1", AgentReply.PROGRESS) is True
        assert store.validate_reply("agent1", AgentReply.BLOCKER) is True

    def test_accept_reply_ready_candidate_transitions(self, store):
        store.set_state("agent1", StreamState.ASSIGNED)
        store.set_state("agent1", StreamState.WORKING)
        record = store.accept_reply("agent1", AgentReply.READY_CANDIDATE)
        assert record.state == StreamState.READY_CANDIDATE

    def test_accept_reply_invalid_raises(self, store):
        # Agent in NEW state, trying PROGRESS (not allowed)
        with pytest.raises(InvalidReplyError):
            store.accept_reply("agent1", AgentReply.PROGRESS)

    def test_list_all(self, store):
        store.set_state("a1", StreamState.ASSIGNED)
        store.set_state("a2", StreamState.ASSIGNED)
        store.set_state("a2", StreamState.WORKING)
        records = store.list_all()
        assert len(records) == 2
        agents = {r.agent for r in records}
        assert agents == {"a1", "a2"}

    def test_list_blocked(self, store):
        store.set_state("a1", StreamState.ASSIGNED)
        store.set_state("a1", StreamState.WORKING)
        store.set_state("a1", StreamState.BLOCKED_LOCAL_QUALITY_GATE)
        store.set_state("a2", StreamState.ASSIGNED)
        store.set_state("a2", StreamState.WORKING)
        blocked = store.list_blocked()
        assert len(blocked) == 1
        assert blocked[0].agent == "a1"

    def test_list_by_state(self, store):
        store.set_state("a1", StreamState.ASSIGNED)
        store.set_state("a1", StreamState.WORKING)
        store.set_state("a2", StreamState.ASSIGNED)
        working = store.list_by_state(StreamState.WORKING)
        assert len(working) == 1
        assigned = store.list_by_state(StreamState.ASSIGNED)
        assert len(assigned) == 1

    def test_persistence(self, store):
        store.set_state("persist-test", StreamState.ASSIGNED)
        store.set_state("persist-test", StreamState.WORKING)

        # New store instance, same dir
        store2 = StreamStateStore(control_dir=store._control_dir)
        record = store2.get("persist-test")
        assert record.state == StreamState.WORKING

    def test_merged_is_terminal(self, store):
        store.set_state("a1", StreamState.ASSIGNED)
        store.set_state("a1", StreamState.WORKING)
        store.set_state("a1", StreamState.READY_CANDIDATE)
        store.set_state("a1", StreamState.READY_FOR_REVIEW, head_sha="abc")
        store.set_state("a1", StreamState.MERGED)
        # No transitions from MERGED
        with pytest.raises(InvalidTransitionError):
            store.set_state("a1", StreamState.WORKING)

    def test_blocked_to_working(self, store):
        store.set_state("a1", StreamState.ASSIGNED)
        store.set_state("a1", StreamState.WORKING)
        store.set_state("a1", StreamState.BLOCKED_SCOPE_POLICY)
        record = store.set_state("a1", StreamState.WORKING, reason="Scope fixed")
        assert record.state == StreamState.WORKING

    def test_all_states_have_transition_rules(self):
        """Every StreamState must be in TRANSITIONS dict."""
        for state in StreamState:
            assert state in TRANSITIONS, f"Missing transition for {state}"

    def test_all_states_have_reply_matrix(self):
        """Every StreamState must be in STATE_REPLY_MATRIX."""
        for state in StreamState:
            assert state in STATE_REPLY_MATRIX, f"Missing reply matrix for {state}"


# ── Worktree Sentinel Tests (unit, no real git needed) ────────

class TestWorktreeSentinelUnit:

    def test_can_mutate_read_only_always_allowed(self, tmp_dir):
        from curaops.control.worktree_sentinel import WorktreeSentinel
        reg_dir = _make_registry_dir(tmp_dir, agent_id="joker")
        sentinel = WorktreeSentinel(control_dir=reg_dir)
        # Read-only operations are always allowed
        assert sentinel.can_mutate("joker", "git status") is True
        assert sentinel.can_mutate("joker", "cat README.md") is True
        assert sentinel.can_mutate("joker", "ls") is True

    def test_can_mutate_mutating_blocked_for_active_agent(self, tmp_dir):
        from curaops.control.worktree_sentinel import WorktreeSentinel
        reg_dir = _make_registry_dir(tmp_dir, agent_id="joker", worktree="/tmp/nonexistent")
        sentinel = WorktreeSentinel(control_dir=reg_dir)
        # Mutating operations blocked for active agent
        assert sentinel.can_mutate("joker", "pytest") is False
        assert sentinel.can_mutate("joker", "sonar") is False
        assert sentinel.can_mutate("joker", "npm install") is False

    def test_can_mutate_destructive_always_blocked(self, tmp_dir):
        from curaops.control.worktree_sentinel import WorktreeSentinel
        reg_dir = _make_registry_dir(tmp_dir, agent_id="joker")
        sentinel = WorktreeSentinel(control_dir=reg_dir)
        # Destructive always blocked
        assert sentinel.can_mutate("joker", "rm -rf something") is False
        assert sentinel.can_mutate("joker", "git clean -fd") is False

    def test_can_mutate_allowed_for_inactive_agent(self, tmp_dir):
        from curaops.control.worktree_sentinel import WorktreeSentinel
        from curaops.control.registry import AgentRegistry, AgentRecord, AgentStatus
        reg_dir = _make_registry_dir(tmp_dir, agent_id="stopped-agent")
        # Set status to stopped via registry API
        reg = AgentRegistry(control_dir=reg_dir)
        reg.update("stopped-agent", status=AgentStatus.STOPPED)
        sentinel = WorktreeSentinel(control_dir=reg_dir)
        # Mutating allowed for stopped agent
        assert sentinel.can_mutate("stopped-agent", "pytest") is True

    def test_inspect_nonexistent_worktree(self, tmp_dir):
        from curaops.control.worktree_sentinel import WorktreeSentinel
        reg_dir = _make_registry_dir(tmp_dir, agent_id="joker", worktree="/tmp/nonexistent-wt-xyz")
        sentinel = WorktreeSentinel(control_dir=reg_dir)
        report = sentinel.inspect("joker")
        assert report.exists is False
        assert len(report.errors) > 0

    def test_inspect_nonexistent_agent(self, tmp_dir):
        from curaops.control.worktree_sentinel import WorktreeSentinel
        reg_dir = _make_registry_dir(tmp_dir, agent_id="joker")
        sentinel = WorktreeSentinel(control_dir=reg_dir)
        report = sentinel.inspect("nonexistent")
        assert report.exists is False

    def test_inspect_real_worktree(self, tmp_dir):
        from curaops.control.worktree_sentinel import WorktreeSentinel
        # Create a real git repo
        import subprocess
        wt = tmp_dir / "worktree"
        wt.mkdir()
        subprocess.run(["git", "init"], cwd=str(wt), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(wt), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(wt), capture_output=True)
        (wt / "hello.py").write_text("print('hello')")
        subprocess.run(["git", "add", "."], cwd=str(wt), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(wt), capture_output=True)

        reg_dir = _make_registry_dir(tmp_dir, agent_id="joker", worktree=str(wt))
        sentinel = WorktreeSentinel(control_dir=reg_dir)
        report = sentinel.inspect("joker")
        assert report.exists is True
        assert report.is_git_repo is True
        assert report.is_clean is True
        assert report.head_sha != ""
