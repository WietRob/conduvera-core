"""Cycle 49 safety reconstruction and explicit release gate tests."""

import pytest

from buildroom_backend_policy import BackendPolicyError, require_backend_enabled
from buildroom_cycle49_preflight import (
    SafetySnapshot,
    WorkerObservation,
    classify_worker,
    release_hold,
)


def safe_snapshot(**overrides) -> SafetySnapshot:
    values = {
        "main_green": True,
        "no_conflicting_active_workers": True,
        "no_active_cycle48_worker": True,
        "no_ambiguous_board_binding": True,
        "origin_main_contains_cycle48_merge": True,
        "working_state_policy_passes": True,
        "projectpack_autonomous": True,
    }
    values.update(overrides)
    return SafetySnapshot(**values)


def test_terminal_cycle48_builder_does_not_count_as_active():
    obs = WorkerObservation(
        task_id="t_deadbeef",
        board="audit-remediation",
        profile="builder",
        task_status="done",
        run_status="done",
        worker_pid=None,
        worker_alive=False,
        workspace="/repo",
        cycle=48,
        project_matches=True,
        historical_preserved=False,
    )
    result = classify_worker(obs, completed_cycles={48})
    assert result.classification == "TERMINAL_NOT_RECONCILED"
    assert result.conflicts_with_project is False


def test_preserved_historical_task_is_not_active():
    obs = WorkerObservation(
        task_id="t_deadbeef",
        board="audit-remediation",
        profile="reviewer",
        task_status="blocked",
        run_status="blocked",
        worker_pid=None,
        worker_alive=False,
        workspace="/repo",
        cycle=48,
        project_matches=True,
        historical_preserved=True,
    )
    result = classify_worker(obs, completed_cycles={48})
    assert result.classification == "HISTORICAL_PRESERVED"
    assert result.conflicts_with_project is False


def test_genuine_running_project_builder_counts():
    obs = WorkerObservation(
        task_id="t_feedface",
        board="audit-remediation",
        profile="builder",
        task_status="running",
        run_status="running",
        worker_pid=123,
        worker_alive=True,
        workspace="/repo",
        cycle=49,
        project_matches=True,
        historical_preserved=False,
    )
    result = classify_worker(obs, completed_cycles={48})
    assert result.classification == "ACTIVE_VALID"
    assert result.conflicts_with_project is True


def test_unrelated_running_builder_is_valid_but_not_conflicting():
    obs = WorkerObservation(
        task_id="t_feedface",
        board="audit-remediation",
        profile="builder",
        task_status="running",
        run_status="running",
        worker_pid=123,
        worker_alive=True,
        workspace="/other-repo",
        cycle=None,
        project_matches=False,
        historical_preserved=False,
    )
    result = classify_worker(obs, completed_cycles={48})
    assert result.classification == "ACTIVE_VALID"
    assert result.conflicts_with_project is False


@pytest.mark.parametrize(
    "failed_gate",
    [
        "main_green",
        "no_conflicting_active_workers",
        "no_active_cycle48_worker",
        "no_ambiguous_board_binding",
        "origin_main_contains_cycle48_merge",
        "working_state_policy_passes",
        "projectpack_autonomous",
    ],
)
def test_cycle49_cannot_release_while_any_gate_fails(failed_gate):
    state = {
        "cycle": 49,
        "phase": "RESEARCHER",
        "status": "HOLD_FOR_BOSS",
        "blocker": "REPEATED_NO_PROGRESS",
        "root_blocker": "SAFETY_GATES:main_green,active_builders",
        "current_candidate": None,
        "task_bindings": {},
    }
    with pytest.raises(ValueError, match="HOLD_RELEASE_BLOCKED"):
        release_hold(state, safe_snapshot(**{failed_gate: False}), evidence_path="/evidence.json")
    assert state["status"] == "HOLD_FOR_BOSS"


def test_release_is_explicit_and_does_not_dispatch_candidate():
    state = {
        "cycle": 49,
        "phase": "RESEARCHER",
        "status": "HOLD_FOR_BOSS",
        "blocker": "REPEATED_NO_PROGRESS",
        "root_blocker": "SAFETY_GATES:main_green,active_builders",
        "current_candidate": None,
        "task_bindings": {},
    }
    release_hold(state, safe_snapshot(), evidence_path="/evidence.json")
    assert state["status"] == "NEXT_CYCLE"
    assert state["hold_release"]["result"] == "HOLD_RELEASED_AFTER_SAFETY_RECONCILIATION"
    assert state["hold_release"]["evidence_path"] == "/evidence.json"
    assert state["current_candidate"] is None
    assert state["task_bindings"] == {}


def test_external_cli_backends_remain_blocked():
    for backend in ("codex_cli", "opencode_cli"):
        with pytest.raises(BackendPolicyError, match=f"BACKEND_DISABLED_BY_OWNER:{backend}"):
            require_backend_enabled(backend)
