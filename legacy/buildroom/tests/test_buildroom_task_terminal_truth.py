"""Task-terminal truth and exact task-bound evidence contract."""

import json
from pathlib import Path

import pytest

from buildroom_core import ProjectPack
from buildroom_task_binding import TaskBinding, store_task_binding
from buildroom_task_terminal import (
    PhaseEvidenceExpectation,
    TaskTerminalState,
    classify_kanban_status,
    evaluate_phase_completion,
)
from peekxd_buildroom_loop_v20 import BuildroomOrchestrator


def expectation(*, task_id="t_f123abc", board="audit-remediation", phase="REVIEWER"):
    return PhaseEvidenceExpectation(
        task_id=task_id,
        board=board,
        cycle=49,
        phase=phase,
        role=phase,
        repo="WietRob/peekxd-linux-computer-use",
        git_head="a" * 40,
        git_base=("b" * 40 if phase in ("BUILDER", "REVIEWER") else None),
        reviewer_verdict_required=phase == "REVIEWER",
    )


def write_evidence(path: Path, expected: PhaseEvidenceExpectation, **overrides):
    record = {
        "schema": "buildroom-task-evidence-v1",
        "task_id": expected.task_id,
        "board": expected.board,
        "cycle": expected.cycle,
        "phase": expected.phase,
        "role": expected.role,
        "repo": expected.repo,
        "git_head": expected.git_head,
        "git_base": expected.git_base,
        "verdict": "APPROVE_MERGE" if expected.reviewer_verdict_required else None,
        "result": "COMPLETE",
    }
    record.update(overrides)
    path.write_text(f"report\n```json\n{json.dumps(record)}\n```\n")
    return path


@pytest.mark.parametrize("status", ["done", "completed"])
def test_success_states_are_success_terminal(status):
    assert classify_kanban_status(status) is TaskTerminalState.SUCCESS_TERMINAL


@pytest.mark.parametrize("status", ["blocked", "gave_up", "crashed", "failed"])
def test_failure_states_are_failure_terminal(status):
    assert classify_kanban_status(status) is TaskTerminalState.FAILURE_TERMINAL


@pytest.mark.parametrize("status", ["todo", "ready", "running", "waiting"])
def test_nonterminal_states_are_pending(status):
    assert classify_kanban_status(status) is TaskTerminalState.PENDING


def test_unknown_state_fails_closed():
    assert classify_kanban_status("mystery") is TaskTerminalState.INCONSISTENT


def test_blocked_reviewer_with_existing_stale_evidence_cannot_complete(tmp_path):
    expected = expectation()
    path = write_evidence(tmp_path / "stale.md", expected)
    result = evaluate_phase_completion("blocked", path, expected)
    assert result.complete is False
    assert result.reason == "TASK_TERMINAL_FAILURE:blocked"


def test_crashed_builder_with_previous_evidence_cannot_create_pr(tmp_path):
    expected = expectation(phase="BUILDER")
    path = write_evidence(tmp_path / "old-builder.md", expected)
    result = evaluate_phase_completion("crashed", path, expected)
    assert result.complete is False
    assert result.reason == "TASK_TERMINAL_FAILURE:crashed"


def test_gave_up_dreamer_with_prior_candidate_evidence_cannot_advance(tmp_path):
    expected = expectation(phase="DREAMER")
    path = write_evidence(tmp_path / "old-dreamer.md", expected)
    result = evaluate_phase_completion("gave_up", path, expected)
    assert result.complete is False
    assert result.reason == "TASK_TERMINAL_FAILURE:gave_up"


def test_replaced_task_evidence_cannot_satisfy_fresh_task(tmp_path):
    expected = expectation(task_id="t_f123abc")
    path = write_evidence(tmp_path / "replaced.md", expected, task_id="t_old123")
    result = evaluate_phase_completion("done", path, expected)
    assert result.complete is False
    assert result.reason == "TASK_EVIDENCE_INVALID:TASK_ID_MISMATCH"


def test_same_task_id_on_wrong_board_cannot_complete(tmp_path):
    expected = expectation(board="audit-remediation")
    path = write_evidence(tmp_path / "wrong-board.md", expected, board="default")
    result = evaluate_phase_completion("done", path, expected)
    assert result.complete is False
    assert result.reason == "TASK_EVIDENCE_INVALID:BOARD_MISMATCH"


def test_successful_task_with_exact_bound_evidence_completes(tmp_path):
    expected = expectation()
    path = write_evidence(tmp_path / "exact.md", expected)
    result = evaluate_phase_completion("completed", path, expected)
    assert result.complete is True
    assert result.reason == "PHASE_COMPLETE"


def test_successful_task_without_evidence_enters_no_progress_path(tmp_path):
    result = evaluate_phase_completion("done", tmp_path / "missing.md", expectation())
    assert result.complete is False
    assert result.reason == "TASK_DONE_BUT_NO_EVIDENCE"


def test_pending_task_with_evidence_is_rejected(tmp_path):
    expected = expectation(phase="RESEARCHER")
    path = write_evidence(tmp_path / "early.md", expected)
    result = evaluate_phase_completion("running", path, expected)
    assert result.complete is False
    assert result.reason == "EVIDENCE_BEFORE_TASK_SUCCESS"


def test_reviewer_requires_binding_verdict(tmp_path):
    expected = expectation()
    path = write_evidence(tmp_path / "no-verdict.md", expected, verdict=None)
    result = evaluate_phase_completion("done", path, expected)
    assert result.complete is False
    assert result.reason == "TASK_EVIDENCE_INVALID:REVIEWER_VERDICT_REQUIRED"


def integration_orchestrator(tmp_path, evidence_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    pack = ProjectPack.from_mapping(
        {
            "project_name": "terminal-integration",
            "repo_path": str(repo),
            "evidence_dir": str(tmp_path / "evidence"),
            "kanban_board": "audit-remediation",
            "default_branch": "main",
            "autopilot_enabled": False,
            "delivery_mode": "engineering_finish_line",
            "allowed_phases": ["RESEARCHER"],
            "profiles": {
                "researcher": "researcher", "builder": "builder", "reviewer": "reviewer"
            },
            "execution": {"builder_backend": "native", "reviewer_backend": "native"},
        }
    )
    orchestrator = BuildroomOrchestrator(pack)
    binding = TaskBinding(
        task_id="t_f123abc", board="audit-remediation", phase="RESEARCHER",
        cycle=49, created_at="2026-07-15T20:00:00Z",
        evidence_path=str(evidence_path), dispatched_head="a" * 40,
        repo="WietRob/peekxd-linux-computer-use", default_branch="main",
    )
    orchestrator.state.update({"cycle": 49, "phase": "RESEARCHER", "task_bindings": {}})
    store_task_binding(orchestrator.state, binding)
    orchestrator.kanban_check_task = lambda _binding: ("completed", "status: completed")
    orchestrator._phase_git_truth = lambda *_args: ("a" * 40, None)
    return orchestrator


def test_orchestrator_phase_completion_uses_exact_bound_evidence(tmp_path):
    path = tmp_path / "evidence" / "researcher" / "researcher-cycle-49-task-t_f123abc.md"
    path.parent.mkdir(parents=True)
    write_evidence(path, expectation(phase="RESEARCHER"))
    orchestrator = integration_orchestrator(tmp_path, path)
    assert orchestrator.check_phase_complete("RESEARCHER", 49) == (True, "PHASE_COMPLETE")


def test_orchestrator_rejects_wrong_board_in_exact_bound_evidence(tmp_path):
    path = tmp_path / "evidence" / "researcher" / "researcher-cycle-49-task-t_f123abc.md"
    path.parent.mkdir(parents=True)
    write_evidence(path, expectation(phase="RESEARCHER"), board="default")
    orchestrator = integration_orchestrator(tmp_path, path)
    complete, reason = orchestrator.check_phase_complete("RESEARCHER", 49)
    assert complete is False
    assert reason == "TASK_EVIDENCE_INVALID:BOARD_MISMATCH"


def test_reviewer_request_fix_is_complete_but_not_merge_approval(tmp_path):
    path = tmp_path / "evidence" / "reviewer" / "reviewer-cycle-49-task-t_f123abc.md"
    path.parent.mkdir(parents=True)
    expected = expectation(phase="REVIEWER")
    write_evidence(path, expected, verdict="REQUEST_FIX")
    orchestrator = integration_orchestrator(tmp_path, path)
    binding = TaskBinding(
        task_id="t_f123abc", board="audit-remediation", phase="REVIEWER",
        cycle=49, created_at="2026-07-15T20:00:00Z",
        evidence_path=str(path), dispatched_head="a" * 40,
        repo="WietRob/peekxd-linux-computer-use", default_branch="main",
    )
    orchestrator.state["task_bindings"] = {}
    orchestrator.state["pr_open"] = "https://github.com/WietRob/peekxd-linux-computer-use/pull/49"
    store_task_binding(orchestrator.state, binding)
    orchestrator._phase_git_truth = lambda *_args: ("a" * 40, "b" * 40)
    orchestrator._validate_phase_execution_evidence = lambda *_args, **_kwargs: True
    assert orchestrator.check_phase_complete("REVIEWER", 49) == (True, "PHASE_COMPLETE")
