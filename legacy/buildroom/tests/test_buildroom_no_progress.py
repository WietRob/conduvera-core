"""Fail-closed no-progress breaker tests for Buildroom reconciliation."""

from pathlib import Path

from buildroom_kanban_paths import resolve_task_log
from buildroom_no_progress import observe_reconciliation
from peekxd_buildroom_loop_v20 import BuildroomOrchestrator


def state() -> dict:
    return {
        "cycle": 48,
        "phase": "REVIEWER",
        "status": "WAITING",
        "blocker": None,
        "pr_open": "https://github.com/WietRob/peekxd-linux-computer-use/pull/41",
        "task_bindings": {
            "REVIEWER": {
                "task_id": "t_0dd",
                "board": "audit-remediation",
                "phase": "REVIEWER",
                "cycle": 48,
                "created_at": "2026-07-15T00:00:00+00:00",
            }
        },
    }


def observe(current: dict, *, task_id: str = "t_0dd", evidence: str = "", log: str = "log-a"):
    return observe_reconciliation(
        current,
        phase="REVIEWER",
        status="WAITING",
        blocker="TASK_DONE_BUT_NO_EVIDENCE",
        task_id=task_id,
        task_board="audit-remediation",
        evidence_fingerprint=evidence,
        log_fingerprint=log,
        threshold=3,
    )


def test_first_two_identical_observations_remain_waiting():
    current = state()
    first = observe(current)
    second = observe(current)
    assert first.terminal_hold is False
    assert second.terminal_hold is False
    assert second.count == 2
    assert current["status"] == "WAITING"


def test_third_identical_observation_enters_terminal_hold():
    current = state()
    observe(current)
    observe(current)
    third = observe(current)
    assert third.terminal_hold is True
    assert third.count == 3
    assert current["status"] == "HOLD_FOR_BOSS"
    assert current["blocker"] == "REPEATED_NO_PROGRESS"
    assert current["root_blocker"] == "TASK_DONE_BUT_NO_EVIDENCE"
    assert current["no_progress"]["root_blocker"] == "TASK_DONE_BUT_NO_EVIDENCE"
    assert current["no_progress"]["first_observed_at"]
    assert current["no_progress"]["last_observed_at"]
    assert current["no_progress"]["task_binding"] == {
        "task_id": "t_0dd",
        "board": "audit-remediation",
    }
    assert current["no_progress"]["evidence_fingerprint"] == ""
    assert current["no_progress"]["log_fingerprint"] == "log-a"


def test_new_evidence_resets_counter():
    current = state()
    observe(current)
    observe(current)
    result = observe(current, evidence="sha256:new-review-evidence")
    assert result.terminal_hold is False
    assert result.count == 0
    assert current["status"] == "WAITING"


def test_fresh_replacement_task_resets_counter():
    current = state()
    observe(current)
    observe(current)
    current["task_bindings"]["REVIEWER"]["task_id"] = "t_fresh"
    result = observe(current, task_id="t_fresh")
    assert result.terminal_hold is False
    assert result.count == 1
    assert current["status"] == "WAITING"


def test_terminal_hold_never_merges_or_transitions_phase():
    current = state()
    original_pr = current["pr_open"]
    observe(current)
    observe(current)
    observe(current)
    assert current["phase"] == "REVIEWER"
    assert current["pr_open"] == original_pr
    assert "MERGE" not in current.get("task_bindings", {})


def test_peekxd_reviewer_reconciliation_uses_generic_terminal_hold():
    orchestrator = object.__new__(BuildroomOrchestrator)
    orchestrator.state = state()
    orchestrator.kanban_get_task_log = lambda _binding: "unchanged worker log"
    orchestrator.save_state = lambda: None

    first = orchestrator.record_no_progress("REVIEWER", "TASK_DONE_BUT_NO_EVIDENCE")
    second = orchestrator.record_no_progress("REVIEWER", "TASK_DONE_BUT_NO_EVIDENCE")
    third = orchestrator.record_no_progress("REVIEWER", "TASK_DONE_BUT_NO_EVIDENCE")

    assert first.terminal_hold is False
    assert second.terminal_hold is False
    assert third.terminal_hold is True
    assert orchestrator.state["phase"] == "REVIEWER"
    assert orchestrator.state["status"] == "HOLD_FOR_BOSS"
    assert orchestrator.state["blocker"] == "REPEATED_NO_PROGRESS"


def test_exact_board_worker_log_is_resolved_without_legacy_global_fallback(tmp_path):
    scoped = tmp_path / ".hermes/kanban/boards/peekxd/logs/t_deadbeef.log"
    scoped.parent.mkdir(parents=True)
    scoped.write_text("binding verdict", encoding="utf-8")
    legacy = tmp_path / ".hermes/kanban/logs/t_deadbeef.log"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("legacy", encoding="utf-8")

    assert resolve_task_log(tmp_path, "t_deadbeef", "peekxd") == scoped.resolve()


def test_safety_gate_no_progress_uses_live_status_and_enters_hold():
    orchestrator = object.__new__(BuildroomOrchestrator)
    orchestrator.state = state()
    orchestrator.state["phase"] = "RESEARCHER"
    orchestrator.state["status"] = "NEXT_CYCLE"
    orchestrator.state["task_bindings"] = {}
    orchestrator.save_state = lambda: None

    for _ in range(3):
        result = orchestrator.record_no_progress(
            "RESEARCHER", "SAFETY_GATES:main_green,active_builders"
        )

    assert result.terminal_hold is True
    assert orchestrator.state["no_progress"]["fingerprint"][1] == "NEXT_CYCLE"
    assert orchestrator.state["status"] == "HOLD_FOR_BOSS"
    assert orchestrator.state["blocker"] == "REPEATED_NO_PROGRESS"


def test_autopilot_runner_stops_immediately_on_terminal_hold():
    runner = (Path(__file__).parents[1] / "buildroom_autopilot_runner.sh").read_text()
    hold_gate = 'if [[ "$STATUS" == HOLD_FOR_BOSS ]]'
    assert hold_gate in runner
    assert runner.index(hold_gate) < runner.index("no state change this tick")
