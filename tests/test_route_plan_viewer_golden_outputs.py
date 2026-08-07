"""Golden output regression tests for Matrix UI route-plan viewer."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from conduvera.cli.main import app
from conduvera.harness.route_plan_viewer import build_route_plan_view, render_route_plan_view

runner = CliRunner()
ROUTE_PLAN_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "harness" / "route_plan"
VIEW_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "harness" / "route_plan_view"

VIEW_FIXTURES = {
    "agent-task": "agent-task.txt",
    "dangerous-file-operation": "dangerous-file-operation.txt",
    "failed-agent-run": "failed-agent-run.txt",
    "operator-ui-view": "operator-ui-view.txt",
    "unknown-intent": "unknown-intent.txt",
}
BANNED_OUTPUT_PHRASES = [
    "runtime execution claim",
    "shell execution",
    "SSH",
    "Raspberry Pi",
    "pi-hermes",
]


def _route_plan_json_path(case_name: str) -> Path:
    return ROUTE_PLAN_FIXTURE_DIR / f"{case_name}.json"


def _viewer_output_path(case_name: str) -> Path:
    return VIEW_FIXTURE_DIR / VIEW_FIXTURES[case_name]


def _read_expected(case_name: str) -> str:
    return _viewer_output_path(case_name).read_text(encoding="utf-8")


def test_every_route_plan_json_fixture_has_viewer_output_fixture() -> None:
    route_plan_cases = {path.stem for path in ROUTE_PLAN_FIXTURE_DIR.glob("*.json")}
    viewer_cases = {path.stem for path in VIEW_FIXTURE_DIR.glob("*.txt")}

    assert route_plan_cases == viewer_cases == set(VIEW_FIXTURES)


def test_rendered_route_plan_views_exactly_match_golden_outputs() -> None:
    for case_name in VIEW_FIXTURES:
        view = build_route_plan_view(_route_plan_json_path(case_name))
        rendered = render_route_plan_view(view)

        assert rendered == _read_expected(case_name)


def test_cli_route_plan_view_outputs_exactly_match_golden_outputs() -> None:
    for case_name in VIEW_FIXTURES:
        result = runner.invoke(
            app,
            ["harness", "route-plan-view", "--input", str(_route_plan_json_path(case_name))],
        )

        assert result.exit_code == 0
        assert result.output == _read_expected(case_name)


def test_viewer_golden_outputs_keep_non_execution_boundaries() -> None:
    for case_name in VIEW_FIXTURES:
        output = _read_expected(case_name)

        assert "Runtime execution: no" in output
        assert "Production dashboard claim: no" in output
        assert "Production dashboard claim: yes" not in output
        for banned_phrase in BANNED_OUTPUT_PHRASES:
            assert banned_phrase not in output


def test_viewer_golden_outputs_capture_operator_scenarios() -> None:
    agent_task = _read_expected("agent-task")
    assert "Matrix UI Route Plan Viewer Stub" in agent_task
    assert "Intent: Run agent task with evidence capture" in agent_task
    assert "Chosen candidate: hermes" in agent_task
    assert "Candidate ranking: hermes, opencode, pi-agent-harness, agent-evidence-plane" in agent_task
    assert "change_request.evidence.generated" in agent_task
    assert "accountable_change.evidence.generated" in agent_task
    assert "agent.run.completed" in agent_task
    assert "Approval gate: CCC/AAL approval before any future execution" in agent_task

    dangerous_action = _read_expected("dangerous-file-operation")
    assert "Chosen candidate: safety-guard" in dangerous_action
    assert "safety_guard.action.blocked" in dangerous_action
    assert "Approval gate: Safety Guard evidence review before any destructive action" in dangerous_action

    failed_run = _read_expected("failed-agent-run")
    assert "Chosen candidate: failure-driven-loop" in failed_run
    assert "failure.observed" in failed_run
    assert "rule.proposed" in failed_run
    assert "rule proposal is evidence-only and is not enforced" in failed_run

    ui_view = _read_expected("operator-ui-view")
    assert "Chosen candidate: matrix-ui-code-editor" in ui_view
    assert "future UI handoff" in ui_view
    assert "Production dashboard claim: no" in ui_view

    unknown_intent = _read_expected("unknown-intent")
    assert "Chosen candidate: none" in unknown_intent
    assert "Fail closed: yes" in unknown_intent
    assert "Unknown capabilities: intent.classification" in unknown_intent
    assert "Approval gate: Human route decision required" in unknown_intent
