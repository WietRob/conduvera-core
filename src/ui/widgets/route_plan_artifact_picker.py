"""Read-only Textual-compatible route-plan artifact picker widget.

The picker lists canonical route-plan artifacts and marks the selected artifact.
It is construction-only and does not start live Textual behavior, browse files,
generate route plans, or execute anything.
"""

from __future__ import annotations

from dataclasses import dataclass

from textual.widgets import Static

from conduvera.harness.route_plan_artifacts import (
    RoutePlanArtifact,
    build_route_plan_artifact_picker_state,
)


@dataclass(frozen=True)
class MatrixRoutePlanArtifactPickerModel:
    """Display-only picker/list model over canonical route-plan artifacts."""

    schema_version: str
    selected_artifact_id: str
    selected_label: str
    selected_scenario: str
    artifacts: list[RoutePlanArtifact]
    selected_marker: str
    runtime_execution: bool
    dynamic_user_file_loading: bool
    arbitrary_filesystem_browser: bool
    route_plan_generation: bool
    dashboard_claim: bool
    widget_boundary: str


def build_route_plan_artifact_picker_model(
    selected_artifact_id: str | None = None,
) -> MatrixRoutePlanArtifactPickerModel:
    """Build a read-only picker/list model for canonical artifacts."""

    state = build_route_plan_artifact_picker_state(selected_artifact_id)
    return MatrixRoutePlanArtifactPickerModel(
        schema_version="matrix-ui-route-plan-artifact-picker.v1",
        selected_artifact_id=state.selected_artifact_id,
        selected_label=state.selected_label,
        selected_scenario=state.selected_scenario,
        artifacts=list(state.artifacts),
        selected_marker="▶",
        runtime_execution=False,
        dynamic_user_file_loading=False,
        arbitrary_filesystem_browser=False,
        route_plan_generation=False,
        dashboard_claim=False,
        widget_boundary="Read-only picker/list widget; no live switching, runtime, file browser, route-plan generation, or dashboard is started.",
    )


def render_route_plan_artifact_picker_text(model: MatrixRoutePlanArtifactPickerModel) -> str:
    """Render deterministic picker/list text for tests and non-live UI composition."""

    artifact_lines = []
    for artifact in model.artifacts:
        marker = model.selected_marker if artifact.artifact_id == model.selected_artifact_id else " "
        artifact_lines.append(f"{marker} {artifact.artifact_id} — {artifact.label} ({artifact.scenario})")

    return "\n".join(
        [
            "Route Plan Artifact Picker",
            f"Schema: {model.schema_version}",
            f"Selected artifact: {model.selected_artifact_id}",
            f"Selected label: {model.selected_label}",
            f"Selected scenario: {model.selected_scenario}",
            "Available artifacts:",
            *artifact_lines,
            f"Runtime execution: {'yes' if model.runtime_execution else 'no'}",
            f"Dynamic user file loading: {'yes' if model.dynamic_user_file_loading else 'no'}",
            f"Arbitrary filesystem browser: {'yes' if model.arbitrary_filesystem_browser else 'no'}",
            f"Route-plan generation: {'yes' if model.route_plan_generation else 'no'}",
            f"Dashboard claim: {'yes' if model.dashboard_claim else 'no'}",
            f"Widget boundary: {model.widget_boundary}",
            "",
        ]
    )


class MatrixRoutePlanArtifactPicker(Static):
    """Non-interactive Textual widget shell for route-plan artifact selection state."""

    DEFAULT_CSS = """
    MatrixRoutePlanArtifactPicker {
        background: rgba(0, 15, 0, 0.9);
        color: #00FF00;
        border: round #00AA00;
        padding: 1;
    }
    """

    def __init__(self, picker_model: MatrixRoutePlanArtifactPickerModel, **kwargs) -> None:
        self.picker_model = picker_model
        self.renderable = render_route_plan_artifact_picker_text(picker_model)
        super().__init__(self.renderable, **kwargs)

    @classmethod
    def from_selected_artifact(
        cls,
        artifact_id: str | None = None,
        **kwargs,
    ) -> MatrixRoutePlanArtifactPicker:
        """Construct a display-only picker widget for a canonical artifact id."""

        return cls(build_route_plan_artifact_picker_model(artifact_id), **kwargs)
