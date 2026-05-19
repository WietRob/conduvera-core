"""Tests for the non-live route-plan artifact picker list widget."""

from __future__ import annotations

import pytest

from src.ui.widgets.route_plan_artifact_picker import (
    MatrixRoutePlanArtifactPicker,
    build_route_plan_artifact_picker_model,
    render_route_plan_artifact_picker_text,
)

EXPECTED_IDS = [
    "agent-task",
    "dangerous-file-operation",
    "failed-agent-run",
    "operator-ui-view",
    "unknown-intent",
]


def test_picker_model_lists_exactly_canonical_artifacts() -> None:
    model = build_route_plan_artifact_picker_model()

    assert [artifact.artifact_id for artifact in model.artifacts] == EXPECTED_IDS
    assert model.schema_version == "matrix-ui-route-plan-artifact-picker.v1"


def test_selected_artifact_is_visually_marked() -> None:
    model = build_route_plan_artifact_picker_model("agent-task")

    rendered = render_route_plan_artifact_picker_text(model)

    assert "▶ agent-task" in rendered


def test_selected_artifact_metadata_is_rendered() -> None:
    model = build_route_plan_artifact_picker_model("operator-ui-view")

    rendered = render_route_plan_artifact_picker_text(model)

    assert "Selected artifact: operator-ui-view" in rendered
    assert "Selected label: Operator UI view handoff" in rendered
    assert "Selected scenario: operator wants UI view" in rendered


def test_non_selected_artifacts_are_rendered_without_selected_marker() -> None:
    model = build_route_plan_artifact_picker_model("agent-task")

    rendered = render_route_plan_artifact_picker_text(model)

    assert "  dangerous-file-operation" in rendered
    assert "▶ dangerous-file-operation" not in rendered
    assert "  failed-agent-run" in rendered
    assert "▶ failed-agent-run" not in rendered


def test_unknown_artifact_id_fails_closed() -> None:
    with pytest.raises(KeyError, match="Unknown route-plan artifact"):
        build_route_plan_artifact_picker_model("not-a-fixture")


def test_widget_render_output_includes_non_live_boundaries() -> None:
    model = build_route_plan_artifact_picker_model("failed-agent-run")

    rendered = render_route_plan_artifact_picker_text(model)

    assert "Runtime execution: no" in rendered
    assert "Dynamic user file loading: no" in rendered
    assert "Arbitrary filesystem browser: no" in rendered
    assert "Route-plan generation: no" in rendered
    assert "Dashboard claim: no" in rendered


def test_static_widget_shell_is_construction_only() -> None:
    widget = MatrixRoutePlanArtifactPicker.from_selected_artifact("dangerous-file-operation")

    assert widget.picker_model.selected_artifact_id == "dangerous-file-operation"
    assert "▶ dangerous-file-operation" in widget.renderable
    assert "Runtime execution: no" in widget.renderable
