"""Golden-output tests for Matrix UI route-plan panel rendering."""

from __future__ import annotations

from pathlib import Path

from src.ui.widgets.route_plan_panel import (
    MatrixRoutePlanPanel,
    build_route_plan_panel,
    render_route_plan_panel_text,
)

ROUTE_PLAN_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "harness" / "route_plan"
PANEL_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "harness" / "route_plan_panel"
CANONICAL_STEMS = {
    "agent-task",
    "dangerous-file-operation",
    "failed-agent-run",
    "operator-ui-view",
    "unknown-intent",
}


def test_canonical_route_plan_fixtures_have_matching_panel_golden_fixtures() -> None:
    route_plan_stems = {path.stem for path in ROUTE_PLAN_FIXTURE_DIR.glob("*.json")}
    panel_stems = {path.stem for path in PANEL_FIXTURE_DIR.glob("*.txt")}

    assert route_plan_stems == CANONICAL_STEMS
    assert panel_stems == CANONICAL_STEMS


def test_panel_renderer_matches_golden_outputs_exactly() -> None:
    for stem in sorted(CANONICAL_STEMS):
        panel = build_route_plan_panel(ROUTE_PLAN_FIXTURE_DIR / f"{stem}.json")
        rendered = render_route_plan_panel_text(panel)
        expected = (PANEL_FIXTURE_DIR / f"{stem}.txt").read_text(encoding="utf-8")

        assert rendered == expected


def test_panel_golden_outputs_preserve_non_execution_boundaries() -> None:
    forbidden_positive_claims = [
        "Runtime execution claim: yes",
        "Production dashboard claim: yes",
        "SSH",
        "Raspberry Pi",
        "pi-hermes",
        "Home-Control",
        "Shell execution: yes",
    ]

    for path in sorted(PANEL_FIXTURE_DIR.glob("*.txt")):
        output = path.read_text(encoding="utf-8")

        assert "Runtime execution: no" in output
        assert "Production dashboard claim: no" in output
        assert "Shell execution: no" in output
        assert "Destructive command path: no" in output
        assert "Panel boundary:" in output
        assert "Display-only" in output
        assert "no live UI route" in output
        for forbidden in forbidden_positive_claims:
            assert forbidden not in output


def test_agent_task_panel_snapshot_preserves_operator_evidence_fields() -> None:
    output = (PANEL_FIXTURE_DIR / "agent-task.txt").read_text(encoding="utf-8")

    assert "hermes" in output
    assert "change_request.evidence.generated" in output
    assert "accountable_change.evidence.generated" in output
    assert "agent.run.completed" in output


def test_dangerous_file_operation_panel_snapshot_preserves_safety_boundary() -> None:
    output = (PANEL_FIXTURE_DIR / "dangerous-file-operation.txt").read_text(encoding="utf-8")

    assert "safety-guard" in output
    assert "safety_guard.action.blocked" in output
    assert "destructive action boundary" in output


def test_failed_agent_run_panel_snapshot_preserves_evidence_only_rule_proposal() -> None:
    output = (PANEL_FIXTURE_DIR / "failed-agent-run.txt").read_text(encoding="utf-8")

    assert "failure-driven-loop" in output
    assert "failure.observed" in output
    assert "rule.proposed" in output
    assert "evidence-only" in output
    assert "not enforced" in output


def test_operator_ui_view_panel_snapshot_preserves_future_ui_boundary() -> None:
    output = (PANEL_FIXTURE_DIR / "operator-ui-view.txt").read_text(encoding="utf-8")

    assert "matrix-ui-code-editor" in output
    assert "future UI handoff boundary" in output
    assert "not a live panel" in output


def test_unknown_intent_panel_snapshot_preserves_fail_closed_human_decision() -> None:
    output = (PANEL_FIXTURE_DIR / "unknown-intent.txt").read_text(encoding="utf-8")

    assert "Chosen candidate: none" in output
    assert "Fail closed: yes" in output
    assert "Human route decision required" in output
    assert "intent.classification" in output


def test_panel_widget_can_be_constructed_from_route_plan_file_without_live_app() -> None:
    widget = MatrixRoutePlanPanel.from_route_plan_file(ROUTE_PLAN_FIXTURE_DIR / "agent-task.json")
    expected = (PANEL_FIXTURE_DIR / "agent-task.txt").read_text(encoding="utf-8")

    assert widget.renderable == expected
    assert widget.panel_model.chosen_candidate_id == "hermes"
