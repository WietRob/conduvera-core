"""Read-only Matrix UI route-plan viewer tests."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from curaops.cli.main import app
from curaops.harness.route_plan_viewer import build_route_plan_view, render_route_plan_view

runner = CliRunner()
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "harness" / "route_plan"


def test_route_plan_view_consumes_agent_task_fixture_without_runtime_claim() -> None:
    view = build_route_plan_view(FIXTURE_DIR / "agent-task.json")

    assert view.schema_version == "matrix-ui-route-plan-view.v1"
    assert view.source_schema_version == "route-plan.v1"
    assert view.intent == "Run agent task with evidence capture"
    assert view.chosen_candidate_id == "hermes"
    assert view.candidate_ranking[:3] == ["hermes", "opencode", "pi-agent-harness"]
    assert view.required_evidence_outputs == [
        "change_request.evidence.generated",
        "accountable_change.evidence.generated",
        "agent.run.completed",
    ]
    assert view.required_approval_gate == "CCC/AAL approval before any future execution"
    assert view.execute_now is False
    assert view.runtime_execution is False
    assert view.dashboard_claim is False
    assert "No runner" in view.non_execution_boundary


def test_route_plan_view_fails_closed_for_unknown_intent_fixture() -> None:
    view = build_route_plan_view(FIXTURE_DIR / "unknown-intent.json")

    assert view.chosen_candidate_id is None
    assert view.fail_closed is True
    assert view.candidate_ranking == []
    assert view.required_approval_gate == "Human route decision required"
    assert view.unknown_capabilities == ["intent.classification"]
    assert view.execute_now is False
    assert view.runtime_execution is False


def test_route_plan_view_renders_operator_facing_stub() -> None:
    view = build_route_plan_view(FIXTURE_DIR / "dangerous-file-operation.json")
    rendered = render_route_plan_view(view)

    assert "Matrix UI Route Plan Viewer Stub" in rendered
    assert "Source schema: route-plan.v1" in rendered
    assert "Intent: dangerous file operation delete production database" in rendered
    assert "Chosen candidate: safety-guard" in rendered
    assert "Candidate ranking: safety-guard" in rendered
    assert "Evidence requirements: safety_guard.action.blocked" in rendered
    assert "Approval gate: Safety Guard evidence review before any destructive action" in rendered
    assert "Runtime execution: no" in rendered
    assert "Production dashboard claim: no" in rendered
    assert "Display-only view over an existing route-plan JSON artifact" in rendered


def test_cli_harness_route_plan_view_reads_existing_json_fixture() -> None:
    result = runner.invoke(
        app,
        ["harness", "route-plan-view", "--input", str(FIXTURE_DIR / "operator-ui-view.json")],
    )

    assert result.exit_code == 0
    assert "Matrix UI Route Plan Viewer Stub" in result.output
    assert "Intent: operator wants UI view of harness status" in result.output
    assert "Chosen candidate: matrix-ui-code-editor" in result.output
    assert "Runtime execution: no" in result.output
    assert "Production dashboard claim: no" in result.output


def test_route_plan_view_rejects_non_route_plan_schema(tmp_path: Path) -> None:
    bad_input = tmp_path / "bad-route-plan.json"
    bad_input.write_text('{"schema_version": "wrong.v1"}\n', encoding="utf-8")

    result = runner.invoke(app, ["harness", "route-plan-view", "--input", str(bad_input)])

    assert result.exit_code == 1
    assert "route-plan-view failed" in result.output
    assert "expected route-plan.v1" in result.output


def test_route_plan_view_rejects_execution_enabled_source_contract(tmp_path: Path) -> None:
    bad_input = tmp_path / "execution-enabled-route-plan.json"
    bad_input.write_text(
        """
        {
          "schema_version": "route-plan.v1",
          "intent": {"text": "Run agent task with evidence capture"},
          "chosen_candidate_id": "hermes",
          "execute_now": true,
          "fail_closed": false,
          "required_approval_gate": "CCC/AAL approval before any future execution",
          "non_execution_boundary": "No runner is executed.",
          "required_evidence_outputs": [],
          "unknown_capabilities": [],
          "candidates": [
            {"candidate_id": "hermes", "rank": 1, "runtime_enabled": true}
          ],
          "steps": [
            {"step_id": "bad", "execute_now": true}
          ]
        }
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["harness", "route-plan-view", "--input", str(bad_input)])

    assert result.exit_code == 1
    assert "route-plan-view failed" in result.output
    assert "route-plan.v1 execute_now must be false" in result.output
