"""Failure-terminal Buildroom tasks stop immediately without no-progress ticks."""

from pathlib import Path

import pytest

from buildroom_core import ProjectPack
from peekxd_buildroom_loop_v20 import BuildroomOrchestrator, BuildroomRunResult


PHASES = ["RESEARCHER", "DREAMER", "BUILDER", "REVIEWER", "MERGE", "REPORTER"]


def make_orchestrator(tmp_path: Path, monkeypatch, phase: str) -> BuildroomOrchestrator:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    pack = ProjectPack.from_mapping(
        {
            "project_name": "terminal-truth",
            "repo_path": str(repo),
            "evidence_dir": str(tmp_path / "evidence"),
            "autopilot_enabled": False,
            "delivery_mode": "engineering_finish_line",
            "kanban_board": "audit-remediation",
            "allowed_phases": PHASES,
            "profiles": {
                "researcher": "researcher", "dreamer": "dreamer",
                "builder": "builder", "reviewer": "reviewer", "reporter": "orchestrator",
            },
            "execution": {"builder_backend": "native", "reviewer_backend": "native"},
        }
    )
    instance = BuildroomOrchestrator(pack)
    instance.state.update({"cycle": 49, "phase": phase, "status": "WAITING", "no_progress": {"count": 0}})
    monkeypatch.setattr(instance, "acquire_lock", lambda: True)
    monkeypatch.setattr(instance, "release_lock", lambda: None)
    monkeypatch.setattr(instance, "reconcile_state", lambda: None)
    monkeypatch.setattr(instance, "save_state", lambda: None)
    monkeypatch.setattr(
        instance, "safety_checks",
        lambda: {"main_green": True, "open_prs": True, "active_builders": True,
                 "no_revert_policy": True, "no_revert_missing_profiles": []},
    )
    return instance


@pytest.mark.parametrize(
    ("phase", "terminal_status"),
    [("REVIEWER", "blocked"), ("BUILDER", "crashed"), ("DREAMER", "gave_up")],
)
def test_failure_terminal_immediately_holds_without_no_progress_increment(
    tmp_path, monkeypatch, phase, terminal_status
):
    instance = make_orchestrator(tmp_path, monkeypatch, phase)
    monkeypatch.setattr(
        instance, "check_phase_complete",
        lambda *_args: (False, f"TASK_TERMINAL_FAILURE:{terminal_status}"),
    )
    monkeypatch.setattr(instance, "maybe_retry_phase", lambda *_args: (False, "non_retryable_failure:UNKNOWN"))
    monkeypatch.setattr(
        instance, "record_no_progress",
        lambda *_args: pytest.fail("terminal failure must not use no-progress"),
    )
    monkeypatch.setattr(
        instance, "orchestrator_push_and_create_pr",
        lambda *_args: pytest.fail("failed Builder must not create PR"),
    )
    monkeypatch.setattr(
        instance, "transition_to_phase",
        lambda *_args: pytest.fail("failure-terminal task must not advance"),
    )

    result = instance.run(autonomous=False, reconcile=False)

    assert result is BuildroomRunResult.PROJECTPACK_BLOCKED
    assert instance.state["status"] == "HOLD_FOR_BOSS"
    assert instance.state["blocker"] == f"TASK_TERMINAL_FAILURE:{terminal_status}:UNKNOWN"
    assert instance.state["no_progress"]["count"] == 0


def test_permitted_bounded_retry_replaces_immediate_hold(tmp_path, monkeypatch):
    instance = make_orchestrator(tmp_path, monkeypatch, "REVIEWER")
    monkeypatch.setattr(
        instance, "check_phase_complete",
        lambda *_args: (False, "TASK_TERMINAL_FAILURE:failed"),
    )
    monkeypatch.setattr(instance, "maybe_retry_phase", lambda *_args: (True, "OK"))
    monkeypatch.setattr(
        instance, "record_no_progress",
        lambda *_args: pytest.fail("terminal retry must not use no-progress"),
    )

    result = instance.run(autonomous=False, reconcile=False)

    assert result is BuildroomRunResult.PHASE_EXECUTED
    assert instance.state["no_progress"]["count"] == 0
