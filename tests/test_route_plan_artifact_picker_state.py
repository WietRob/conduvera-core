"""Tests for non-live route-plan artifact picker UI state."""

from __future__ import annotations

import pytest

from conduvera.harness.route_plan_artifacts import (
    build_route_plan_artifact_picker_state,
    render_route_plan_artifact_picker_state,
)

EXPECTED_IDS = [
    "agent-task",
    "dangerous-file-operation",
    "failed-agent-run",
    "operator-ui-view",
    "unknown-intent",
]


def test_picker_state_defaults_to_agent_task_and_lists_canonical_artifacts() -> None:
    state = build_route_plan_artifact_picker_state()

    assert state.schema_version == "route-plan-artifact-picker.v1"
    assert state.selected_artifact_id == "agent-task"
    assert state.selected_label == "Agent task with evidence capture"
    assert state.selected_scenario == "AI-assisted code change"
    assert [artifact.artifact_id for artifact in state.artifacts] == EXPECTED_IDS


def test_picker_state_can_select_each_canonical_artifact() -> None:
    expected_scenarios = {
        "agent-task": "AI-assisted code change",
        "dangerous-file-operation": "dangerous file operation",
        "failed-agent-run": "failed agent run",
        "operator-ui-view": "operator wants UI view",
        "unknown-intent": "fail-closed unknown intent",
    }

    for artifact_id, expected_scenario in expected_scenarios.items():
        state = build_route_plan_artifact_picker_state(artifact_id)

        assert state.selected_artifact_id == artifact_id
        assert state.selected_scenario == expected_scenario
        assert state.boundary == "read-only selector; display-only; no runtime execution"
        assert state.runtime_execution is False
        assert state.dynamic_user_file_loading is False
        assert state.arbitrary_filesystem_browser is False
        assert state.route_plan_generation is False


def test_picker_state_unknown_artifact_fails_closed() -> None:
    with pytest.raises(KeyError, match="Unknown route-plan artifact"):
        build_route_plan_artifact_picker_state("not-a-fixture")


def test_picker_state_render_shows_selected_artifact_and_boundaries() -> None:
    state = build_route_plan_artifact_picker_state("dangerous-file-operation")

    rendered = render_route_plan_artifact_picker_state(state)

    assert "Route Plan Artifact Picker State" in rendered
    assert "Selected artifact: dangerous-file-operation" in rendered
    assert "Selected label: Dangerous file operation safety gate" in rendered
    assert "Selected scenario: dangerous file operation" in rendered
    assert "Available artifacts: agent-task, dangerous-file-operation, failed-agent-run, operator-ui-view, unknown-intent" in rendered
    assert "Runtime execution: no" in rendered
    assert "Dynamic user file loading: no" in rendered
    assert "Arbitrary filesystem browser: no" in rendered
    assert "Route-plan generation: no" in rendered
    assert "Dashboard claim: no" in rendered
