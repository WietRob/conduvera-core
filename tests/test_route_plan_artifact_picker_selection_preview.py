"""Tests for construction-only selected-artifact preview switching."""

from __future__ import annotations

import pytest

from curaops.harness.route_plan_artifacts import CANONICAL_ROUTE_PLAN_ARTIFACT_IDS
from src.ui.widgets.route_plan_artifact_picker import (
    build_route_plan_artifact_selection_preview,
)


def _selected_line(rendered: str) -> str:
    return next(line for line in rendered.splitlines() if line.startswith("▶ "))


def test_selection_preview_can_be_constructed_for_each_canonical_artifact() -> None:
    for artifact_id in CANONICAL_ROUTE_PLAN_ARTIFACT_IDS:
        preview = build_route_plan_artifact_selection_preview(artifact_id)

        assert preview.selected_artifact_id == artifact_id
        assert preview.picker_model.selected_artifact_id == artifact_id
        assert preview.panel_model.source_schema_version == "route-plan.v1"
        assert preview.runtime_execution is False
        assert preview.dynamic_user_file_loading is False
        assert preview.arbitrary_filesystem_browser is False
        assert preview.route_plan_generation is False
        assert preview.dashboard_claim is False


def test_selection_preview_switch_changes_selected_marker_id_label_and_scenario() -> None:
    agent_task = build_route_plan_artifact_selection_preview("agent-task")
    dangerous = build_route_plan_artifact_selection_preview("dangerous-file-operation")

    assert _selected_line(agent_task.picker_renderable).startswith("▶ agent-task")
    assert _selected_line(dangerous.picker_renderable).startswith("▶ dangerous-file-operation")
    assert agent_task.selected_artifact_id == "agent-task"
    assert dangerous.selected_artifact_id == "dangerous-file-operation"
    assert agent_task.selected_label == "Agent task with evidence capture"
    assert dangerous.selected_label == "Dangerous file operation safety gate"
    assert agent_task.selected_scenario == "AI-assisted code change"
    assert dangerous.selected_scenario == "dangerous file operation"


def test_selection_preview_switch_changes_panel_body_not_just_picker_header() -> None:
    agent_task = build_route_plan_artifact_selection_preview("agent-task")
    dangerous = build_route_plan_artifact_selection_preview("dangerous-file-operation")

    assert agent_task.panel_renderable != dangerous.panel_renderable
    assert "Chosen candidate: hermes" in agent_task.panel_renderable
    assert "Chosen candidate: safety-guard" in dangerous.panel_renderable
    assert "destructive action boundary" not in agent_task.panel_renderable
    assert "destructive action boundary" in dangerous.panel_renderable


def test_selection_preview_combined_renderable_keeps_picker_and_panel_source_specific() -> None:
    preview = build_route_plan_artifact_selection_preview("failed-agent-run")

    assert preview.renderable.startswith("Route Plan Artifact Picker")
    assert "Selected artifact: failed-agent-run" in preview.renderable
    assert "Matrix UI Route Plan Panel Model" in preview.renderable
    assert "Chosen candidate: failure-driven-loop" in preview.renderable
    assert "failed-run review; rule proposal is evidence-only and is not enforced" in preview.renderable
    assert "Chosen candidate: hermes" not in preview.panel_renderable


def test_selection_preview_unknown_artifact_id_fails_closed() -> None:
    with pytest.raises(KeyError, match="Unknown route-plan artifact"):
        build_route_plan_artifact_selection_preview("not-a-fixture")


def test_selection_preview_is_construction_only_and_boundary_flags_stay_false() -> None:
    preview = build_route_plan_artifact_selection_preview("unknown-intent")

    assert preview.panel_model.fail_closed is True
    assert preview.runtime_execution is False
    assert preview.dynamic_user_file_loading is False
    assert preview.arbitrary_filesystem_browser is False
    assert preview.route_plan_generation is False
    assert preview.dashboard_claim is False
    assert "Runtime execution: no" in preview.renderable
    assert "Dynamic user file loading: no" in preview.renderable
    assert "Arbitrary filesystem browser: no" in preview.renderable
    assert "Route-plan generation: no" in preview.renderable
    assert "Production dashboard claim: no" in preview.renderable
