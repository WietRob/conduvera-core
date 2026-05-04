"""
Tests for CuraOps-Control: Registry, EventLog, Gates, Adapters.
"""
import json
import tempfile
from pathlib import Path

import pytest

from curaops.control.registry import AgentRegistry, AgentRecord, AgentStatus
from curaops.control.eventlog import EventLog, ControlEvent
from curaops.control.gates import (
    GateRunner, GateProfile, GateResult, GateStatus, GateRunResult,
    DirtyWorktreeGate, ScopeCheckGate, BUILTIN_GATES,
)
from curaops.control.adapters.manual import ManualAdapter


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def tmp_control(tmp_path):
    """Create a temporary control directory."""
    d = tmp_path / ".curaops" / "control"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def registry(tmp_control):
    return AgentRegistry(control_dir=tmp_control)


@pytest.fixture
def eventlog(tmp_control):
    return EventLog(control_dir=tmp_control)


@pytest.fixture
def sample_agent():
    return AgentRecord(
        agent_id="Batman",
        tool="opencode",
        task="TASK-I198",
        issue=200,
        worktree="/tmp/test-wt",
        gate_profile="default",
        status=AgentStatus.ACTIVE,
    )


# ═══════════════════════════════════════════════════════════════════
# REGISTRY TESTS
# ═══════════════════════════════════════════════════════════════════

class TestAgentRegistry:

    def test_register_and_get(self, registry, sample_agent):
        registry.register(sample_agent)
        got = registry.get("Batman")
        assert got is not None
        assert got.agent_id == "Batman"
        assert got.tool == "opencode"
        assert got.task == "TASK-I198"

    def test_register_duplicate_raises(self, registry, sample_agent):
        registry.register(sample_agent)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(sample_agent)

    def test_get_nonexistent(self, registry):
        assert registry.get("NoSuchAgent") is None

    def test_update(self, registry, sample_agent):
        registry.register(sample_agent)
        updated = registry.update("Batman", task="TASK-I199")
        assert updated.task == "TASK-I199"

    def test_update_nonexistent_raises(self, registry):
        with pytest.raises(KeyError, match="not found"):
            registry.update("Ghost", task="x")

    def test_remove(self, registry, sample_agent):
        registry.register(sample_agent)
        assert registry.remove("Batman") is True
        assert registry.get("Batman") is None

    def test_remove_nonexistent(self, registry):
        assert registry.remove("Ghost") is False

    def test_list_all(self, registry):
        for name in ["Batman", "Bricktop", "Droid"]:
            registry.register(AgentRecord(agent_id=name, tool="manual", task=f"TASK-{name}"))
        agents = registry.list_all()
        assert len(agents) == 3
        names = {a.agent_id for a in agents}
        assert names == {"Batman", "Bricktop", "Droid"}

    def test_list_by_status(self, registry):
        a1 = AgentRecord(agent_id="A", tool="manual", task="T1", status=AgentStatus.ACTIVE)
        a2 = AgentRecord(agent_id="B", tool="manual", task="T2", status=AgentStatus.BLOCKED)
        registry.register(a1)
        registry.register(a2)
        active = registry.list_by_status(AgentStatus.ACTIVE)
        assert len(active) == 1
        assert active[0].agent_id == "A"

    def test_list_active_excludes_stopped(self, registry):
        for name, status in [("A", AgentStatus.ACTIVE), ("B", AgentStatus.STOPPED), ("C", AgentStatus.CRASHED)]:
            registry.register(AgentRecord(agent_id=name, tool="manual", task="T", status=status))
        active = registry.list_active()
        assert len(active) == 1
        assert active[0].agent_id == "A"

    def test_status_transitions(self, registry, sample_agent):
        registry.register(sample_agent)
        registry.set_ready("Batman", evidence={"test": True})
        assert registry.get("Batman").status == AgentStatus.READY

        registry.set_blocked("Batman", "sonar failed")
        assert registry.get("Batman").status == AgentStatus.BLOCKED
        assert registry.get("Batman").blocked_reason == "sonar failed"

        registry.set_stopped("Batman")
        assert registry.get("Batman").status == AgentStatus.STOPPED

    def test_to_json(self, registry, sample_agent):
        registry.register(sample_agent)
        j = registry.to_json()
        data = json.loads(j)
        assert "agents" in data
        assert "Batman" in data["agents"]

    def test_find_by_task(self, registry):
        registry.register(AgentRecord(agent_id="A", tool="manual", task="TASK-X1"))
        registry.register(AgentRecord(agent_id="B", tool="manual", task="TASK-X2"))
        result = registry.find_by_task("TASK-X1")
        assert len(result) == 1
        assert result[0].agent_id == "A"

    def test_find_by_worktree(self, registry):
        registry.register(AgentRecord(agent_id="A", tool="manual", task="T", worktree="/tmp/wt1"))
        registry.register(AgentRecord(agent_id="B", tool="manual", task="T", worktree="/tmp/wt2"))
        result = registry.find_by_worktree("/tmp/wt1")
        assert result is not None
        assert result.agent_id == "A"


# ═══════════════════════════════════════════════════════════════════
# EVENT LOG TESTS
# ═══════════════════════════════════════════════════════════════════

class TestEventLog:

    def test_append_and_read(self, eventlog):
        event = ControlEvent(
            timestamp="2026-05-04T12:00:00+00:00",
            event_type="boot",
            agent_id="Batman",
            detail="Booted",
        )
        eventlog.append(event)
        events = eventlog.read_all()
        assert len(events) == 1
        assert events[0].agent_id == "Batman"
        assert events[0].event_type == "boot"

    def test_log_convenience(self, eventlog):
        eventlog.log("boot", "Batman", "Started", extra="info")
        events = eventlog.read_all()
        assert len(events) == 1
        assert events[0].metadata["extra"] == "info"

    def test_read_last(self, eventlog):
        for i in range(10):
            eventlog.log("tick", "captain", f"tick-{i}")
        last5 = eventlog.read_last(5)
        assert len(last5) == 5
        assert last5[-1].detail == "tick-9"

    def test_empty_log(self, eventlog):
        assert eventlog.read_all() == []
        assert eventlog.count() == 0

    def test_count(self, eventlog):
        for i in range(5):
            eventlog.log("tick", "captain", f"t{i}")
        assert eventlog.count() == 5

    def test_events_for_agent(self, eventlog):
        eventlog.log("boot", "Batman", "started")
        eventlog.log("boot", "Bricktop", "started")
        eventlog.log("ready", "Batman", "done")
        batman_events = eventlog.events_for_agent("Batman", limit=10)
        assert len(batman_events) == 2
        assert all(e.agent_id == "Batman" for e in batman_events)

    def test_events_of_type(self, eventlog):
        eventlog.log("boot", "A", "x")
        eventlog.log("ready", "A", "y")
        eventlog.log("boot", "B", "z")
        boots = eventlog.events_of_type("boot", limit=10)
        assert len(boots) == 2


# ═══════════════════════════════════════════════════════════════════
# GATE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestGateProfile:

    def test_from_yaml_dict(self):
        data = {
            "required": ["dirty_worktree", "scope_check"],
            "not_required": ["db_integration"],
            "description": "Test profile",
        }
        profile = GateProfile.from_yaml_dict("test", data)
        assert profile.name == "test"
        assert "dirty_worktree" in profile.required
        assert "db_integration" in profile.not_required


class TestDirtyWorktreeGate:

    def test_clean_worktree_passes(self, tmp_path):
        # Create a clean git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)

        gate = DirtyWorktreeGate()
        result = gate.run({}, str(tmp_path))
        assert result.passed

    def test_dirty_worktree_fails(self, tmp_path):
        import subprocess
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)
        # Make it dirty
        (tmp_path / "new_file.txt").write_text("dirty")

        gate = DirtyWorktreeGate()
        result = gate.run({}, str(tmp_path))
        assert result.status == GateStatus.FAIL

    def test_nonexistent_worktree_errors(self):
        gate = DirtyWorktreeGate()
        result = gate.run({}, "/nonexistent/path")
        assert result.status == GateStatus.ERROR

    def test_no_worktree_errors(self):
        gate = DirtyWorktreeGate()
        result = gate.run({}, "")
        assert result.status == GateStatus.ERROR


class TestScopeCheckGate:

    def test_no_scope_passes(self):
        from curaops.control.gates import ScopeCheckGate
        gate = ScopeCheckGate()
        result = gate.run({"scope_files": []}, "/tmp")
        assert result.passed

    def test_no_worktree_errors(self):
        from curaops.control.gates import ScopeCheckGate
        gate = ScopeCheckGate()
        result = gate.run({"scope_files": ["a.py"]}, "")
        assert result.status == GateStatus.ERROR


class TestGateRunner:

    def test_run_with_default_profile(self, tmp_path):
        # Create gates.yaml
        policies = tmp_path / "policies"
        policies.mkdir()
        (policies / "gates.yaml").write_text("""
gate_profiles:
  default:
    required:
      - dirty_worktree
    not_required: []
""")
        runner = GateRunner(control_dir=tmp_path)
        agent = {"agent_id": "Test", "gate_profile": "default", "worktree": "/nonexistent"}
        result = runner.run_for_agent(agent)
        # dirty_worktree should fail (path doesn't exist) but that's the gate's job
        assert isinstance(result, GateRunResult)
        assert result.agent_id == "Test"

    def test_run_unknown_profile_falls_back(self, tmp_path):
        runner = GateRunner(control_dir=tmp_path)
        agent = {"agent_id": "Test", "gate_profile": "nonexistent", "worktree": ""}
        result = runner.run_for_agent(agent)
        # Falls back to core gates
        assert isinstance(result, GateRunResult)

    def test_list_profiles_empty(self, tmp_path):
        runner = GateRunner(control_dir=tmp_path)
        assert runner.list_profiles() == []

    def test_list_profiles_from_yaml(self, tmp_path):
        policies = tmp_path / "policies"
        policies.mkdir()
        (policies / "gates.yaml").write_text("""
gate_profiles:
  frontend_ui:
    required: [dirty_worktree]
    not_required: []
  full_stack:
    required: [dirty_worktree, class_tests]
    not_required: []
""")
        runner = GateRunner(control_dir=tmp_path)
        profiles = runner.list_profiles()
        assert "frontend_ui" in profiles
        assert "full_stack" in profiles


# ═══════════════════════════════════════════════════════════════════
# ADAPTER TESTS
# ═══════════════════════════════════════════════════════════════════

class TestManualAdapter:

    def test_start_session(self):
        adapter = ManualAdapter()
        result = adapter.start_session("Batman", "/tmp/wt", "TASK-X", {})
        assert result.success
        assert result.detail["session_ref"] == "manual"

    def test_stop_session(self):
        adapter = ManualAdapter()
        result = adapter.stop_session("Batman", "manual")
        assert result.success

    def test_session_status_alive(self):
        adapter = ManualAdapter()
        result = adapter.session_status("Batman", "manual")
        assert result.detail["alive"] is True

    def test_prepare_worktree(self, tmp_path):
        adapter = ManualAdapter()
        wt = tmp_path / "worktree"
        wt.mkdir()
        result = adapter.prepare_worktree("Batman", str(wt), ["a.py", "b.py"], {"task": "T1", "gate_profile": "default"})
        assert result.success
        assert (wt / ".agent-id").read_text() == "Batman"
        assert (wt / ".task-key").read_text() == "T1"
        assert (wt / ".scope").read_text() == "a.py\nb.py"
        assert (wt / ".gate-profile").read_text() == "default"

    def test_prepare_worktree_nonexistent(self):
        adapter = ManualAdapter()
        result = adapter.prepare_worktree("Batman", "/nonexistent", [], {})
        assert not result.success


# ═══════════════════════════════════════════════════════════════════
# INTEGRATION TEST
# ═══════════════════════════════════════════════════════════════════

class TestIntegration:

    def test_full_lifecycle(self, tmp_control):
        registry = AgentRegistry(control_dir=tmp_control)
        eventlog = EventLog(control_dir=tmp_control)

        # 1. Boot
        agent = AgentRecord(agent_id="Batman", tool="manual", task="TASK-X", gate_profile="default")
        registry.register(agent)
        eventlog.log("boot", "Batman", "Booted")

        # 2. Activate
        registry.set_active("Batman")
        assert registry.get("Batman").status == AgentStatus.ACTIVE

        # 3. Ready (skip gates for unit test)
        registry.set_ready("Batman", evidence={"manual": True})
        eventlog.log("ready", "Batman", "Ready")
        assert registry.get("Batman").status == AgentStatus.READY

        # 4. Dispatch new task
        registry.update("Batman", task="TASK-Y")
        registry.set_active("Batman")
        eventlog.log("dispatch", "Batman", "New task: TASK-Y")

        # 5. Block
        registry.set_blocked("Batman", "test failure")
        eventlog.log("blocked", "Batman", "test failure")

        # 6. Stop
        registry.set_stopped("Batman")
        eventlog.log("stopped", "Batman", "Done")

        # Verify full event trail
        events = eventlog.events_for_agent("Batman")
        types = [e.event_type for e in events]
        assert types == ["boot", "ready", "dispatch", "blocked", "stopped"]

        # Verify final state
        final = registry.get("Batman")
        assert final.status == AgentStatus.STOPPED
        assert final.task == "TASK-Y"
