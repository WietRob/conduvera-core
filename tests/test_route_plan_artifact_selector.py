"""Tests for the non-live route-plan artifact selector."""

from __future__ import annotations

from pathlib import Path

import pytest

from curaops.harness.route_plan_artifacts import (
    CANONICAL_ROUTE_PLAN_ARTIFACT_IDS,
    default_route_plan_artifact,
    get_route_plan_artifact,
    list_route_plan_artifacts,
)
from src.ui.widgets.route_plan_panel import MatrixRoutePlanPanel

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "harness" / "route_plan"
EXPECTED_CANDIDATES = {
    "agent-task": "hermes",
    "dangerous-file-operation": "safety-guard",
    "failed-agent-run": "failure-driven-loop",
    "operator-ui-view": "matrix-ui-code-editor",
    "unknown-intent": None,
}


def test_lists_exactly_the_canonical_route_plan_artifacts() -> None:
    artifacts = list_route_plan_artifacts()

    assert [artifact.artifact_id for artifact in artifacts] == CANONICAL_ROUTE_PLAN_ARTIFACT_IDS == [
        "agent-task",
        "dangerous-file-operation",
        "failed-agent-run",
        "operator-ui-view",
        "unknown-intent",
    ]


def test_each_artifact_path_exists_under_canonical_fixture_directory() -> None:
    fixture_root = FIXTURE_DIR.resolve()

    for artifact in list_route_plan_artifacts():
        assert artifact.path.exists()
        assert artifact.path.resolve().is_relative_to(fixture_root)
        assert artifact.path.suffix == ".json"
        assert artifact.boundary == "display-only"


def test_each_artifact_builds_a_valid_non_live_panel() -> None:
    for artifact in list_route_plan_artifacts():
        panel = MatrixRoutePlanPanel.from_route_plan_file(artifact.path)

        assert panel.panel_model.source_schema_version == "route-plan.v1"
        assert panel.panel_model.runtime_execution is False
        assert panel.panel_model.shell_execution is False
        assert panel.panel_model.destructive_command_path is False
        assert panel.panel_model.dashboard_claim is False


def test_unknown_artifact_id_fails_closed() -> None:
    with pytest.raises(KeyError, match="Unknown route-plan artifact"):
        get_route_plan_artifact("../../arbitrary")


def test_default_artifact_is_agent_task() -> None:
    artifact = default_route_plan_artifact()

    assert artifact.artifact_id == "agent-task"
    assert artifact.default_selected is True
    assert artifact.path == FIXTURE_DIR / "agent-task.json"


def test_artifact_metadata_matches_expected_candidate() -> None:
    for artifact_id, expected_candidate in EXPECTED_CANDIDATES.items():
        artifact = get_route_plan_artifact(artifact_id)

        assert artifact.source_schema_version == "route-plan.v1"
        assert artifact.expected_candidate_id == expected_candidate
        if artifact_id == "unknown-intent":
            assert artifact.scenario == "fail-closed unknown intent"
