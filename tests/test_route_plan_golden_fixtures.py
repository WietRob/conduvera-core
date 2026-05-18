"""Golden fixture regression tests for route-plan.v1 handoff JSON."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from curaops.cli.main import app
from curaops.harness.route_plan import plan_route, route_plan_to_dict

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "harness" / "route_plan"

CASES = {
    "agent-task.json": "Run agent task with evidence capture",
    "dangerous-file-operation.json": "dangerous file operation delete production database",
    "failed-agent-run.json": "review failed agent run and propose rule",
    "operator-ui-view.json": "operator wants UI view of harness status",
    "unknown-intent.json": "make the thing better somehow",
}

runner = CliRunner()


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_route_plan_golden_fixtures_exactly_match_contract_output() -> None:
    for fixture_name, intent in CASES.items():
        assert route_plan_to_dict(plan_route(intent)) == _load_fixture(fixture_name)


def test_golden_fixtures_preserve_non_executing_route_plan_contract() -> None:
    for fixture_name in CASES:
        payload = _load_fixture(fixture_name)
        assert payload["schema_version"] == "route-plan.v1"
        assert payload["execute_now"] is False
        assert payload["non_execution_boundary"]
        for candidate in payload["candidates"]:
            assert candidate["runtime_enabled"] is False
        for step in payload["steps"]:
            assert step["execute_now"] is False


def test_agent_task_fixture_documents_operator_handoff_value() -> None:
    payload = _load_fixture("agent-task.json")

    assert payload["chosen_candidate_id"] == "hermes"
    assert payload["required_evidence_outputs"] == [
        "change_request.evidence.generated",
        "accountable_change.evidence.generated",
        "agent.run.completed",
    ]
    assert payload["required_approval_gate"] == "CCC/AAL approval before any future execution"


def test_dangerous_file_operation_fixture_blocks_shell_and_file_execution() -> None:
    payload = _load_fixture("dangerous-file-operation.json")

    assert payload["chosen_candidate_id"] == "safety-guard"
    assert payload["required_evidence_outputs"] == ["safety_guard.action.blocked"]
    assert "No shell command, file deletion, or external tool is executed" in payload["non_execution_boundary"]


def test_failed_agent_run_fixture_keeps_rule_proposal_evidence_only() -> None:
    payload = _load_fixture("failed-agent-run.json")

    assert payload["chosen_candidate_id"] == "failure-driven-loop"
    assert payload["required_evidence_outputs"] == ["failure.observed", "rule.proposed"]
    assert any(step["expected_output"] == "rule.proposed evidence-only" for step in payload["steps"])
    assert payload["required_approval_gate"] == "Human review before any rule adoption or enforcement"


def test_operator_ui_view_fixture_has_no_dashboard_claim() -> None:
    payload = _load_fixture("operator-ui-view.json")

    assert payload["chosen_candidate_id"] == "matrix-ui-code-editor"
    assert "no production dashboard claim" in payload["non_execution_boundary"]


def test_unknown_intent_fixture_fails_closed() -> None:
    payload = _load_fixture("unknown-intent.json")

    assert payload["chosen_candidate_id"] is None
    assert payload["fail_closed"] is True
    assert payload["execute_now"] is False
    assert payload["required_approval_gate"] == "Human route decision required"


def test_cli_json_output_matches_agent_task_golden_fixture() -> None:
    result = runner.invoke(
        app,
        ["harness", "route-plan", "--intent", CASES["agent-task.json"], "--format", "json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == _load_fixture("agent-task.json")


def test_cli_json_output_file_matches_agent_task_golden_fixture() -> None:
    with runner.isolated_filesystem():
        output_path = Path("route-plan.json")
        result = runner.invoke(
            app,
            [
                "harness",
                "route-plan",
                "--intent",
                CASES["agent-task.json"],
                "--format",
                "json",
                "--output",
                str(output_path),
            ],
        )

        assert result.exit_code == 0
        assert json.loads(output_path.read_text(encoding="utf-8")) == _load_fixture("agent-task.json")


def test_unknown_intent_cli_json_exits_2_and_matches_fixture() -> None:
    result = runner.invoke(
        app,
        ["harness", "route-plan", "--intent", CASES["unknown-intent.json"], "--format", "json"],
    )

    assert result.exit_code == 2
    assert json.loads(result.output) == _load_fixture("unknown-intent.json")
