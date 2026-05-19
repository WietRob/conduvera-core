"""Read-only registry for canonical route-plan artifacts.

The selector is intentionally fixture/artifact-scoped: it never walks arbitrary
user paths, generates route plans, or executes candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CANONICAL_ROUTE_PLAN_ARTIFACT_IDS = [
    "agent-task",
    "dangerous-file-operation",
    "failed-agent-run",
    "operator-ui-view",
    "unknown-intent",
]

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "harness" / "route_plan"

_ARTIFACT_METADATA = {
    "agent-task": {
        "label": "Agent task with evidence capture",
        "scenario": "AI-assisted code change",
        "expected_candidate_id": "hermes",
        "default_selected": True,
    },
    "dangerous-file-operation": {
        "label": "Dangerous file operation safety gate",
        "scenario": "dangerous file operation",
        "expected_candidate_id": "safety-guard",
        "default_selected": False,
    },
    "failed-agent-run": {
        "label": "Failed agent run review loop",
        "scenario": "failed agent run",
        "expected_candidate_id": "failure-driven-loop",
        "default_selected": False,
    },
    "operator-ui-view": {
        "label": "Operator UI view handoff",
        "scenario": "operator wants UI view",
        "expected_candidate_id": "matrix-ui-code-editor",
        "default_selected": False,
    },
    "unknown-intent": {
        "label": "Unknown intent fail-closed route",
        "scenario": "fail-closed unknown intent",
        "expected_candidate_id": None,
        "default_selected": False,
    },
}


@dataclass(frozen=True)
class RoutePlanArtifactPickerState:
    """Read-only UI state for the canonical route-plan artifact picker."""

    schema_version: str
    artifacts: list[RoutePlanArtifact]
    selected_artifact_id: str
    selected_label: str
    selected_scenario: str
    boundary: str
    runtime_execution: bool
    dynamic_user_file_loading: bool
    arbitrary_filesystem_browser: bool
    route_plan_generation: bool
    dashboard_claim: bool


@dataclass(frozen=True)
class RoutePlanArtifact:
    """Descriptor for a canonical non-live route-plan artifact."""

    artifact_id: str
    label: str
    path: Path
    scenario: str
    default_selected: bool
    source_schema_version: str
    expected_candidate_id: str | None
    boundary: str = "display-only"


def _artifact_from_id(artifact_id: str) -> RoutePlanArtifact:
    metadata = _ARTIFACT_METADATA[artifact_id]
    return RoutePlanArtifact(
        artifact_id=artifact_id,
        label=metadata["label"],
        path=_FIXTURE_DIR / f"{artifact_id}.json",
        scenario=metadata["scenario"],
        default_selected=bool(metadata["default_selected"]),
        source_schema_version="route-plan.v1",
        expected_candidate_id=metadata["expected_candidate_id"],
    )


def list_route_plan_artifacts() -> list[RoutePlanArtifact]:
    """Return the fixed canonical route-plan artifact list."""

    return [_artifact_from_id(artifact_id) for artifact_id in CANONICAL_ROUTE_PLAN_ARTIFACT_IDS]


def get_route_plan_artifact(artifact_id: str) -> RoutePlanArtifact:
    """Return a canonical artifact descriptor or fail closed for unknown ids."""

    if artifact_id not in _ARTIFACT_METADATA:
        raise KeyError(f"Unknown route-plan artifact: {artifact_id}")
    return _artifact_from_id(artifact_id)


def default_route_plan_artifact() -> RoutePlanArtifact:
    """Return the default selected route-plan artifact."""

    for artifact in list_route_plan_artifacts():
        if artifact.default_selected:
            return artifact
    raise RuntimeError("No default route-plan artifact configured")


def build_route_plan_artifact_picker_state(
    selected_artifact_id: str | None = None,
) -> RoutePlanArtifactPickerState:
    """Build read-only UI state for the canonical artifact picker."""

    artifacts = list_route_plan_artifacts()
    selected = (
        get_route_plan_artifact(selected_artifact_id)
        if selected_artifact_id
        else default_route_plan_artifact()
    )
    return RoutePlanArtifactPickerState(
        schema_version="route-plan-artifact-picker.v1",
        artifacts=artifacts,
        selected_artifact_id=selected.artifact_id,
        selected_label=selected.label,
        selected_scenario=selected.scenario,
        boundary="read-only selector; display-only; no runtime execution",
        runtime_execution=False,
        dynamic_user_file_loading=False,
        arbitrary_filesystem_browser=False,
        route_plan_generation=False,
        dashboard_claim=False,
    )


def render_route_plan_artifact_picker_state(state: RoutePlanArtifactPickerState) -> str:
    """Render deterministic read-only picker state for UI snapshot tests."""

    available = ", ".join(artifact.artifact_id for artifact in state.artifacts)
    return "\n".join(
        [
            "Route Plan Artifact Picker State",
            f"Schema: {state.schema_version}",
            f"Selected artifact: {state.selected_artifact_id}",
            f"Selected label: {state.selected_label}",
            f"Selected scenario: {state.selected_scenario}",
            f"Available artifacts: {available}",
            f"Runtime execution: {'yes' if state.runtime_execution else 'no'}",
            f"Dynamic user file loading: {'yes' if state.dynamic_user_file_loading else 'no'}",
            f"Arbitrary filesystem browser: {'yes' if state.arbitrary_filesystem_browser else 'no'}",
            f"Route-plan generation: {'yes' if state.route_plan_generation else 'no'}",
            f"Dashboard claim: {'yes' if state.dashboard_claim else 'no'}",
            f"Picker boundary: {state.boundary}",
            "",
        ]
    )
