"""v0.26.1 Dreamer Dispatch Repair Tests."""

import json, sys, tempfile, textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path.home() / ".hermes/scripts"))
import peekxd_buildroom_loop_v20 as v20
from peekxd_buildroom_loop_v20 import BuildroomOrchestrator

MAX_RETRIES = 3
v20.MAX_COMPLIANCE_RETRIES = MAX_RETRIES


def _setup(tmpdir, extra_state=None):
    st = Path(tmpdir) / "orchestrator-state.json"
    st.write_text("{}")
    p1 = patch.object(v20, "STATE_FILE", st)
    p1.start()
    ed = Path(tmpdir)
    p2 = patch.object(v20, "EVIDENCE_DIR", ed)
    p2.start()
    o = BuildroomOrchestrator()
    o.safety_checks = MagicMock(return_value={
        "main_green": True,
        "open_prs": True,
        "active_builders": True,
        "no_revert_policy": True,
        "no_revert_missing_profiles": [],
    })
    o.state.update({
        "cycle": 36,
        "phase": "DREAMER",
        "status": "NEXT_PHASE",
        "mode": "FULL_CYCLE_CERTIFICATION",
        "canonical_schema_required": True,
        "compliance_required": True,
        "task_ids": {"RESEARCHER": "t_r_done"},
        "compliance_retries": {},
        "project_pack": str(Path.home() / ".hermes/buildroom/projects/peekxd.yaml"),
        "repo_path": str(Path.home() / "projects/peekxd-linux-computer-use"),
        "evidence_dir": str(tmpdir),
        "strategy_file": "/fake/adr.md",
    })
    if extra_state:
        o.state.update(extra_state)
    (ed / "researcher").mkdir(parents=True, exist_ok=True)
    evidence_path = ed / "researcher" / "researcher-cycle-36-test.md"
    evidence_path.write_text("dummy evidence")
    o.check_bound_evidence = MagicMock(return_value=(True, evidence_path))
    return o, p1, p2


def _mock_kanban_methods(o):
    o.kanban_create = MagicMock(return_value=("t_mock_create", None))
    o.kanban_show = MagicMock(return_value=(True, "ok"))
    o.kanban_dispatch = MagicMock(return_value=(True, "ok"))
    o.kanban_check_task = MagicMock(return_value=("done", "ok"))
    o.kanban_block = MagicMock(return_value=(True, "ok"))
    o.kanban_get_task_log = MagicMock(return_value="no errors")

    def fake_create(title, assignee, body, phase, **_route):
        task_id, error = o.kanban_create(title, assignee, body)
        if not task_id:
            return None, f"CREATE_FAILED: {error}"
        o.state["task_ids"][phase] = task_id
        visible, _ = o.kanban_show(task_id)
        if not visible:
            return None, f"TASK_NOT_VISIBLE: {task_id}"
        dispatched, _ = o.kanban_dispatch(max_tasks=1)
        if not dispatched:
            return None, "DISPATCH_FAILED"
        return task_id, "OK"

    o.create_task_with_verify = MagicMock(side_effect=fake_create)
    o.dispatch_role_execution = MagicMock(
        side_effect=lambda **kwargs: o.create_task_with_verify(
            kwargs["title"],
            kwargs["expected_profile"],
            kwargs["body"],
            kwargs["phase"],
            authorized_route_id="route-test",
            provider="test",
            model="test",
        )
    )
    return o


class TestDreamerDispatchReturnCheck:

    def test_dispatch_success_sets_waiting(self, tmp_path):
        """FULL_CYCLE_CERTIFICATION, phase DREAMER, status NEXT_PHASE dispatches Dreamer task."""
        o, p1, p2 = _setup(tmp_path)
        _mock_kanban_methods(o)
        o.run()
        assert o.state["status"] == "WAITING"
        assert "DREAMER" in o.state["task_ids"]
        p1.stop(); p2.stop()

    def test_dispatch_failure_sets_blocked(self, tmp_path):
        """create_task_with_verify failure sets BLOCKED_DREAMER_DISPATCH_FAILED."""
        o, p1, p2 = _setup(tmp_path)
        _mock_kanban_methods(o)
        o.kanban_create.return_value = (None, "CREATE_FAILED: provider error")
        o.run()
        assert o.state["status"] == "BLOCKED_DREAMER_DISPATCH_FAILED"
        p1.stop(); p2.stop()

    def test_dispatch_failure_does_not_set_waiting(self, tmp_path):
        """Status bleibt BLOCKED, nicht WAITING."""
        o, p1, p2 = _setup(tmp_path)
        _mock_kanban_methods(o)
        o.kanban_create.return_value = (None, "CREATE_FAILED")
        o.run()
        assert o.state["status"] != "WAITING"
        assert o.state["status"] == "BLOCKED_DREAMER_DISPATCH_FAILED"
        p1.stop(); p2.stop()

    def test_dispatch_failure_no_builder_start(self, tmp_path):
        """BLOCKED verhindert Builder-Start — phase bleibt DREAMER."""
        o, p1, p2 = _setup(tmp_path)
        _mock_kanban_methods(o)
        o.kanban_create.return_value = (None, "CREATE_FAILED")
        o.run()
        assert o.state["phase"] == "DREAMER"
        p1.stop(); p2.stop()

    def test_dispatch_failure_no_candidate_set(self, tmp_path):
        """Kein Candidate wird gesetzt ohne Dreamer Evidence."""
        o, p1, p2 = _setup(tmp_path)
        _mock_kanban_methods(o)
        o.kanban_create.return_value = (None, "CREATE_FAILED")
        o.run()
        assert o.state.get("current_candidate") is None
        p1.stop(); p2.stop()

    def test_full_cycle_certification_does_not_block_dreamer(self, tmp_path):
        """Mode Gate blockiert DREAMER in FULL_CYCLE_CERTIFICATION nicht."""
        o, p1, p2 = _setup(tmp_path, {"mode": "FULL_CYCLE_CERTIFICATION"})
        _mock_kanban_methods(o)
        o.run()
        assert o.state["status"] == "WAITING"
        assert o.state["phase"] == "DREAMER"
        assert "DREAMER" in o.state["task_ids"]
        p1.stop(); p2.stop()

    def test_dispatch_view_failure_sets_blocked(self, tmp_path):
        """create_task_with_verify failure on kanban_show sets BLOCKED."""
        o, p1, p2 = _setup(tmp_path)
        _mock_kanban_methods(o)
        o.kanban_show.return_value = (False, "TASK_NOT_VISIBLE: t_xxx")
        o.run()
        assert o.state["status"] == "BLOCKED_DREAMER_DISPATCH_FAILED"
        p1.stop(); p2.stop()

    def test_no_real_kanban_task_spawned(self, tmp_path):
        """Unit Test erzeugt keine echten Kanban Tasks."""
        o, p1, p2 = _setup(tmp_path)
        _mock_kanban_methods(o)
        o.run()
        o.kanban_create.assert_called_once()
        o.kanban_dispatch.assert_called_once()
        p1.stop(); p2.stop()

    def test_no_evidence_file_patched(self, tmp_path):
        """Keine echte Evidence-Datei wird gepatcht."""
        o, p1, p2 = _setup(tmp_path)
        _mock_kanban_methods(o)
        o.run()
        import glob
        evidence_files = list(Path(tmp_path).rglob("dreamer-cycle-36*.md"))
        assert len(evidence_files) == 0, f"Should be 0, got {evidence_files}"
        p1.stop(); p2.stop()


class TestResearcherDispatchReturnCheck:

    def test_researcher_dispatch_failure_sets_blocked(self, tmp_path):
        o, p1, p2 = _setup(tmp_path, {"phase": "RESEARCHER", "status": "NEXT_PHASE"})
        _mock_kanban_methods(o)
        o.kanban_create.return_value = (None, "CREATE_FAILED")
        o.run()
        assert o.state["status"] == "BLOCKED_RESEARCHER_DISPATCH_FAILED"
        p1.stop(); p2.stop()

    def test_researcher_dispatch_success_sets_waiting(self, tmp_path):
        o, p1, p2 = _setup(tmp_path, {"phase": "RESEARCHER", "status": "NEXT_PHASE"})
        _mock_kanban_methods(o)
        o.run()
        assert o.state["status"] == "WAITING"
        assert "RESEARCHER" in o.state["task_ids"]
        p1.stop(); p2.stop()


class TestBuilderDispatchReturnCheck:

    def test_builder_dispatch_failure_sets_blocked(self, tmp_path):
        o, p1, p2 = _setup(tmp_path, {"phase": "BUILDER", "status": "NEXT_PHASE",
            "current_candidate": "test-candidate",
            "task_ids": {"DREAMER": "t_d_one"}})
        (Path(tmp_path) / "dreamer").mkdir(exist_ok=True)
        (Path(tmp_path) / "dreamer" / "dreamer-cycle-36-test.md").write_text("dummy dreamer")
        _mock_kanban_methods(o)
        o.kanban_create.return_value = (None, "CREATE_FAILED")
        o.run()
        assert o.state["status"] == "BLOCKED_BUILDER_DISPATCH_FAILED"
        p1.stop(); p2.stop()

    def test_builder_dispatch_success_sets_waiting(self, tmp_path):
        o, p1, p2 = _setup(tmp_path, {"phase": "BUILDER", "status": "NEXT_PHASE",
            "current_candidate": "test-candidate",
            "task_ids": {"DREAMER": "t_d_one"}})
        (Path(tmp_path) / "dreamer").mkdir(exist_ok=True)
        (Path(tmp_path) / "dreamer" / "dreamer-cycle-36-test.md").write_text("dummy dreamer")
        _mock_kanban_methods(o)
        o.run()
        assert o.state["status"] == "WAITING"
        assert "BUILDER" in o.state["task_ids"]
        p1.stop(); p2.stop()
