"""Dry-run route planning tests for Matrix OS Harness Gateway."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from curaops.cli.main import app
from curaops.harness.route_plan import OperatorIntent, plan_route, render_route_plan, route_plan_to_dict

runner = CliRunner()


def test_ai_assisted_code_change_ranks_agent_candidates_and_requires_accountability_evidence() -> None:
    plan = plan_route(OperatorIntent(text="AI-assisted code change with evidence capture"))

    candidate_ids = [candidate.candidate_id for candidate in plan.candidates]
    assert candidate_ids[:3] == ["hermes", "opencode", "pi-agent-harness"]
    assert plan.chosen_candidate_id == "hermes"
    assert "accountable_change.evidence.generated" in plan.required_evidence_outputs
    assert "change_request.evidence.generated" in plan.required_evidence_outputs
    assert "agent.run.completed" in plan.required_evidence_outputs
    assert plan.required_approval_gate == "CCC/AAL approval before any future execution"
    assert plan.execute_now is False
    assert all(candidate.runtime_enabled is False for candidate in plan.candidates)
    assert all("not executed" in candidate.not_executed_now for candidate in plan.candidates)


def test_dangerous_file_operation_requires_safety_guard_gate_without_destructive_execution() -> None:
    plan = plan_route(OperatorIntent(text="dangerous file operation delete production database"))

    assert plan.chosen_candidate_id == "safety-guard"
    assert "safety_guard.action.blocked" in plan.required_evidence_outputs
    assert plan.required_approval_gate == "Safety Guard evidence review before any destructive action"
    assert plan.execute_now is False
    assert any(step.step_id == "safety-evidence-translation" for step in plan.steps)
    assert "No shell command, file deletion, or external tool is executed" in plan.non_execution_boundary


def test_failed_agent_run_routes_to_failure_loop_evidence_only_without_enforcement() -> None:
    plan = plan_route(OperatorIntent(text="review failed agent run and propose rule"))

    assert plan.chosen_candidate_id == "failure-driven-loop"
    assert "failure.observed" in plan.required_evidence_outputs
    assert "rule.proposed" in plan.required_evidence_outputs
    assert any(step.expected_output == "rule.proposed evidence-only" for step in plan.steps)
    assert plan.required_approval_gate == "Human review before any rule adoption or enforcement"
    assert plan.execute_now is False


def test_operator_ui_view_uses_original_matrix_ui_surfaces_without_dashboard_claim() -> None:
    plan = plan_route(OperatorIntent(text="operator wants UI view of harness status"))

    candidate_ids = [candidate.candidate_id for candidate in plan.candidates]
    assert "matrix-ui-code-editor" in candidate_ids
    assert plan.chosen_candidate_id == "matrix-ui-code-editor"
    assert "harness.status.view" in plan.required_evidence_outputs
    assert "no production dashboard claim" in plan.non_execution_boundary
    assert plan.execute_now is False


def test_unknown_intent_fails_closed_and_needs_human_decision() -> None:
    plan = plan_route(OperatorIntent(text="make the thing better somehow"))

    assert plan.chosen_candidate_id is None
    assert plan.fail_closed is True
    assert plan.required_approval_gate == "Human route decision required"
    assert plan.unknown_capabilities == ("intent.classification",)
    assert plan.execute_now is False
    assert plan.candidates == ()


def test_route_plan_render_and_cli_smoke_show_dry_run_boundaries() -> None:
    plan = plan_route(OperatorIntent(text="Run agent task with evidence capture"))
    rendered = render_route_plan(plan)

    assert "execute_now: false" in rendered
    assert "chosen_candidate: hermes" in rendered
    assert "what_would_execute_later" in rendered
    assert "what_is_not_executed_now" in rendered
    assert "required_evidence_outputs" in rendered

    result = runner.invoke(app, ["harness", "route-plan", "--intent", "Run agent task with evidence capture"])
    assert result.exit_code == 0
    assert "DRY-RUN ROUTE PLAN" in result.output
    assert "execute_now: false" in result.output
    assert "pi-agent-harness" in result.output


def test_route_plan_to_dict_is_stable_machine_readable_contract() -> None:
    plan = plan_route(OperatorIntent(text="Run agent task with evidence capture", correlation_id="route-123"))

    payload = route_plan_to_dict(plan)

    assert payload["schema_version"] == "route-plan.v1"
    assert payload["intent"] == {
        "text": "Run agent task with evidence capture",
        "actor": "operator",
        "correlation_id": "route-123",
    }
    assert payload["execute_now"] is False
    assert payload["fail_closed"] is False
    assert payload["chosen_candidate_id"] == "hermes"
    assert payload["required_approval_gate"] == "CCC/AAL approval before any future execution"
    assert "agent.run.completed" in payload["required_evidence_outputs"]
    assert payload["candidates"][0]["candidate_id"] == "hermes"
    assert payload["candidates"][0]["runtime_enabled"] is False
    assert payload["candidates"][0]["capability_matches"][0] == {
        "capability_id": "route-planning",
        "matched": True,
        "reason": "best descriptor match for agent task orchestration intent",
    }
    assert payload["steps"][0] == {
        "step_id": "classify-intent",
        "description": "Classify as AI-assisted code-change route",
        "expected_output": "route.intent.classified",
        "execute_now": False,
    }


def test_route_plan_cli_json_format_emits_parseable_contract_only() -> None:
    result = runner.invoke(
        app,
        ["harness", "route-plan", "--intent", "Run agent task with evidence capture", "--format", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "route-plan.v1"
    assert payload["intent"]["text"] == "Run agent task with evidence capture"
    assert payload["execute_now"] is False
    assert payload["chosen_candidate_id"] == "hermes"
    assert payload["candidates"][2]["candidate_id"] == "pi-agent-harness"
    assert payload["candidates"][2]["runtime_enabled"] is False
    assert "DRY-RUN ROUTE PLAN" not in result.output


def test_route_plan_cli_output_writes_json_file_without_execution() -> None:
    import tempfile
    import os
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        output_path = Path("route-plan.json")
        result = runner.invoke(
            app,
            [
                "harness",
                "route-plan",
                "--intent",
                "dangerous file operation delete production database",
                "--format",
                "json",
                "--output",
                str(output_path),
            ],
        )

        assert result.exit_code == 0
        assert result.output == f"Wrote dry-run route plan: {output_path}\n"
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload["chosen_candidate_id"] == "safety-guard"
        assert payload["execute_now"] is False
        assert payload["required_evidence_outputs"] == ["safety_guard.action.blocked"]


def test_route_plan_cli_json_unknown_intent_still_fails_closed_with_exit_2() -> None:
    result = runner.invoke(
        app,
        ["harness", "route-plan", "--intent", "make the thing better somehow", "--format", "json"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["fail_closed"] is True
    assert payload["chosen_candidate_id"] is None
    assert payload["unknown_capabilities"] == ["intent.classification"]
    assert payload["execute_now"] is False
