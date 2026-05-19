"""Minimal Textual-compatible route-plan panel model tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ui.widgets.route_plan_panel import (
    MatrixRoutePlanPanel,
    build_route_plan_panel,
    render_route_plan_panel_text,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "harness" / "route_plan"


def test_agent_task_fixture_builds_panel_model_without_runtime_claim() -> None:
    panel = build_route_plan_panel(FIXTURE_DIR / "agent-task.json")

    assert panel.schema_version == "matrix-ui-route-plan-panel.v1"
    assert panel.source_schema_version == "route-plan.v1"
    assert panel.intent == "Run agent task with evidence capture"
    assert panel.chosen_candidate_id == "hermes"
    assert panel.required_evidence_outputs == [
        "change_request.evidence.generated",
        "accountable_change.evidence.generated",
        "agent.run.completed",
    ]
    assert panel.runtime_execution is False
    assert panel.dashboard_claim is False
    assert panel.panel_boundary.startswith("Display-only")


def test_dangerous_file_operation_panel_shows_safety_boundary_without_execution() -> None:
    panel = build_route_plan_panel(FIXTURE_DIR / "dangerous-file-operation.json")
    rendered = render_route_plan_panel_text(panel)

    assert panel.chosen_candidate_id == "safety-guard"
    assert panel.required_evidence_outputs == ["safety_guard.action.blocked"]
    assert "destructive action boundary" in rendered
    assert "Runtime execution: no" in rendered
    assert "Shell execution: no" in rendered
    assert "Destructive command path: no" in rendered


def test_failed_agent_run_panel_keeps_rule_proposal_evidence_only() -> None:
    panel = build_route_plan_panel(FIXTURE_DIR / "failed-agent-run.json")
    rendered = render_route_plan_panel_text(panel)

    assert panel.chosen_candidate_id == "failure-driven-loop"
    assert "failure.observed" in panel.required_evidence_outputs
    assert "rule.proposed" in panel.required_evidence_outputs
    assert "rule proposal is evidence-only and is not enforced" in rendered


def test_operator_ui_view_panel_identifies_future_ui_handoff_without_dashboard_claim() -> None:
    panel = build_route_plan_panel(FIXTURE_DIR / "operator-ui-view.json")
    rendered = render_route_plan_panel_text(panel)

    assert panel.chosen_candidate_id == "matrix-ui-code-editor"
    assert "future UI handoff boundary" in rendered
    assert "Production dashboard claim: no" in rendered
    assert panel.dashboard_claim is False


def test_unknown_intent_panel_fails_closed_for_human_decision() -> None:
    panel = build_route_plan_panel(FIXTURE_DIR / "unknown-intent.json")
    rendered = render_route_plan_panel_text(panel)

    assert panel.fail_closed is True
    assert panel.chosen_candidate_id is None
    assert panel.required_approval_gate == "Human route decision required"
    assert "Chosen candidate: none" in rendered
    assert "Fail closed: yes" in rendered
    assert "Unknown capabilities: intent.classification" in rendered


def test_panel_renderer_is_deterministic_and_keeps_runtime_boundaries() -> None:
    panel = build_route_plan_panel(FIXTURE_DIR / "agent-task.json")
    rendered_once = render_route_plan_panel_text(panel)
    rendered_twice = render_route_plan_panel_text(panel)

    assert rendered_once == rendered_twice
    assert "Matrix UI Route Plan Panel Model" in rendered_once
    assert "Intent: Run agent task with evidence capture" in rendered_once
    assert "Chosen candidate: hermes" in rendered_once
    assert "Runtime execution: no" in rendered_once
    assert "Production dashboard claim: no" in rendered_once
    assert "Panel boundary: Display-only Textual-compatible panel model" in rendered_once


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ('{"schema_version": "wrong.v1"}\n', "expected route-plan.v1"),
        (
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
              "candidates": [],
              "steps": []
            }
            """.strip()
            + "\n",
            "execute_now must be false",
        ),
        (
            """
            {
              "schema_version": "route-plan.v1",
              "intent": {"text": "Run agent task with evidence capture"},
              "chosen_candidate_id": "hermes",
              "execute_now": false,
              "fail_closed": false,
              "required_approval_gate": "CCC/AAL approval before any future execution",
              "non_execution_boundary": "No runner is executed.",
              "required_evidence_outputs": [],
              "unknown_capabilities": [],
              "candidates": [{"candidate_id": "hermes", "runtime_enabled": true}],
              "steps": []
            }
            """.strip()
            + "\n",
            "runtime_enabled must be false",
        ),
        (
            """
            {
              "schema_version": "route-plan.v1",
              "intent": {"text": "Run agent task with evidence capture"},
              "chosen_candidate_id": "hermes",
              "execute_now": false,
              "fail_closed": false,
              "required_approval_gate": "CCC/AAL approval before any future execution",
              "non_execution_boundary": "No runner is executed.",
              "required_evidence_outputs": [],
              "unknown_capabilities": [],
              "candidates": [],
              "steps": [{"step_id": "bad", "execute_now": true}]
            }
            """.strip()
            + "\n",
            "execute_now must be false",
        ),
    ],
)
def test_panel_rejects_invalid_route_plan_inputs(tmp_path: Path, payload: str, expected_error: str) -> None:
    bad_input = tmp_path / "bad-route-plan.json"
    bad_input.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match=expected_error):
        build_route_plan_panel(bad_input)


def test_textual_panel_widget_can_be_constructed_without_running_live_app() -> None:
    panel_model = build_route_plan_panel(FIXTURE_DIR / "agent-task.json")
    widget = MatrixRoutePlanPanel(panel_model)

    assert widget.panel_model == panel_model
    assert "Matrix UI Route Plan Panel Model" in widget.renderable
