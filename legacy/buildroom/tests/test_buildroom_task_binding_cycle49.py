"""Cycle 49 canonical Kanban task/board binding contract."""

from pathlib import Path
from types import SimpleNamespace

import pytest
import peekxd_buildroom_loop_v20 as loop_module

from buildroom_kanban_paths import (
    AmbiguousTaskBoardError,
    resolve_legacy_task_board,
    resolve_task_log,
)
from buildroom_task_binding import (
    TaskBinding,
    binding_for_phase,
    kanban_argv,
    store_task_binding,
)
from peekxd_buildroom_loop_v20 import BuildroomOrchestrator


def binding() -> TaskBinding:
    return TaskBinding(
        task_id="t_deadbeef",
        board="audit-remediation",
        phase="REVIEWER",
        cycle=49,
        created_at="2026-07-15T20:00:00+00:00",
    )


def test_new_task_stores_task_id_plus_board():
    state = {"task_bindings": {}}
    store_task_binding(state, binding())
    assert state["task_bindings"]["REVIEWER"] == {
        "task_id": "t_deadbeef",
        "board": "audit-remediation",
        "phase": "REVIEWER",
        "cycle": 49,
        "created_at": "2026-07-15T20:00:00+00:00",
    }
    assert "task_ids" not in state


def test_orchestrator_create_show_dispatch_reconciliation_are_explicit_board(monkeypatch):
    calls = []

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        operation = argv[4]
        if operation == "create":
            return SimpleNamespace(returncode=0, stdout="Created t_deadbeef\n", stderr="")
        if operation == "show":
            return SimpleNamespace(returncode=0, stdout="status: done\n", stderr="")
        if operation == "comment":
            return SimpleNamespace(returncode=0, stdout="commented\n", stderr="")
        if operation == "dispatch":
            return SimpleNamespace(returncode=0, stdout="dispatched\n", stderr="")
        raise AssertionError(operation)

    monkeypatch.setattr(loop_module, "consume_route_authorization", lambda *a, **k: None)
    monkeypatch.setattr(loop_module.subprocess, "run", fake_run)
    monkeypatch.setenv("HERMES_KANBAN_BOARD", "default")
    orchestrator = object.__new__(BuildroomOrchestrator)
    orchestrator.pack = SimpleNamespace(kanban_board="audit-remediation")
    orchestrator._evidence_dir = Path("/evidence")
    orchestrator._repo_path = Path("/repo")
    orchestrator.evidence_dir = Path("/evidence")
    orchestrator.repo_path = Path("/repo")
    orchestrator.state = {"cycle": 49, "task_bindings": {}}
    orchestrator.save_state = lambda: None
    orchestrator._capture_dispatch_head = lambda: "a" * 40
    orchestrator.project_slug = lambda: "peekxd"

    task_id, result = orchestrator.create_task_with_verify(
        "title", "reviewer", "body", "REVIEWER"
    )

    assert (task_id, result) == ("t_deadbeef", "OK")
    stored = orchestrator.state["task_bindings"]["REVIEWER"]
    assert stored["board"] == "audit-remediation"
    assert stored["evidence_path"] == "/evidence/reviewer/reviewer-cycle-49-task-t_deadbeef.md"
    assert stored["dispatched_head"] == "a" * 40
    assert stored["repo"] == "peekxd"
    assert any(call[4] == "comment" for call in calls)
    create_call = next(call for call in calls if call[4] == "create")
    body = create_call[create_call.index("--body") + 1]
    assert "${KANBAN_TASK_ID}" in body
    assert "run_id=${KANBAN_TASK_ID}" in body
    assert "board=audit-remediation" in body
    assert all(
        call[:4] == ["hermes", "kanban", "--board", "audit-remediation"]
        for call in calls
    )


@pytest.mark.parametrize(
    "operation",
    ["show", "runs", "log", "context", "complete", "block", "unblock", "archive", "comment"],
)
def test_every_task_operation_uses_stored_board(operation):
    argv = kanban_argv(operation, binding())
    assert argv[:4] == ["hermes", "kanban", "--board", "audit-remediation"]
    assert argv[4:] == [operation, "t_deadbeef"]


def test_create_and_dispatch_require_explicit_board():
    assert kanban_argv("create", board="audit-remediation")[:5] == [
        "hermes", "kanban", "--board", "audit-remediation", "create"
    ]
    assert kanban_argv("dispatch", board="audit-remediation")[:5] == [
        "hermes", "kanban", "--board", "audit-remediation", "dispatch"
    ]
    with pytest.raises(ValueError, match="KANBAN_BOARD_REQUIRED"):
        kanban_argv("create")


def test_wrong_current_board_cannot_affect_binding(monkeypatch):
    monkeypatch.setenv("HERMES_KANBAN_BOARD", "default")
    state = {"task_bindings": {"REVIEWER": binding().to_dict()}}
    loaded = binding_for_phase(state, "REVIEWER")
    assert loaded.board == "audit-remediation"
    assert "default" not in kanban_argv("show", loaded)


def test_same_task_id_on_two_boards_is_ambiguous_for_legacy_lookup(tmp_path):
    for board in ("one", "two"):
        log = tmp_path / ".hermes/kanban/boards" / board / "logs/t_deadbeef.log"
        log.parent.mkdir(parents=True)
        log.write_text(board)
    with pytest.raises(AmbiguousTaskBoardError, match="AMBIGUOUS_TASK_BOARD"):
        resolve_legacy_task_board(tmp_path, "t_deadbeef")


def test_current_schema_never_falls_back_to_global_log(tmp_path):
    global_log = tmp_path / ".hermes/kanban/logs/t_deadbeef.log"
    global_log.parent.mkdir(parents=True)
    global_log.write_text("legacy")
    assert resolve_task_log(tmp_path, "t_deadbeef", "audit-remediation") is None


def test_historical_recovery_finds_audit_remediation(tmp_path):
    log = tmp_path / ".hermes/kanban/boards/audit-remediation/logs/t_deadbeef.log"
    log.parent.mkdir(parents=True)
    log.write_text("historical")
    assert resolve_legacy_task_board(tmp_path, "t_deadbeef") == "audit-remediation"
    assert resolve_task_log(tmp_path, "t_deadbeef", "audit-remediation") == log.resolve()


def test_bare_legacy_task_requires_stored_legacy_board():
    with pytest.raises(ValueError, match="TASK_BOARD_REQUIRED"):
        binding_for_phase({"task_ids": {"REVIEWER": "t_deadbeef"}}, "REVIEWER")
    loaded = binding_for_phase(
        {
            "cycle": 48,
            "task_ids": {"REVIEWER": "t_deadbeef"},
            "task_boards": {"REVIEWER": "audit-remediation"},
        },
        "REVIEWER",
    )
    assert loaded.board == "audit-remediation"
