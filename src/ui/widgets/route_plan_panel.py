"""Minimal Textual-compatible route-plan panel model.

This module adapts the validated read-only route-plan viewer model into a
non-interactive panel model that can be mounted by the preserved Matrix UI later.
It does not start a Textual app, execute route candidates, launch adapters, or
claim dashboard behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from textual.widgets import Static

from curaops.harness.route_plan_viewer import MatrixUiRoutePlanView, build_route_plan_view


@dataclass(frozen=True)
class MatrixRoutePlanPanelModel:
    """Display-only Textual-compatible panel model for route-plan.v1 handoffs."""

    schema_version: str
    source_schema_version: str
    intent: str
    chosen_candidate_id: str | None
    candidate_ranking: list[str]
    required_evidence_outputs: list[str]
    required_approval_gate: str
    fail_closed: bool
    unknown_capabilities: list[str]
    runtime_execution: bool
    dashboard_claim: bool
    shell_execution: bool
    destructive_command_path: bool
    non_execution_boundary: str
    panel_boundary: str
    operator_snapshot_note: str


def _operator_snapshot_note(view: MatrixUiRoutePlanView) -> str:
    if view.chosen_candidate_id == "failure-driven-loop":
        return "failed-run review; rule proposal is evidence-only and is not enforced."
    if view.chosen_candidate_id == "matrix-ui-code-editor":
        return "future UI handoff boundary; display-only Matrix UI/editor surface, not a live panel."
    if view.chosen_candidate_id == "safety-guard":
        return "destructive action boundary; safety evidence is required before any future action."
    if view.fail_closed:
        return "fail-closed; human route decision required before any future action."
    return "route-plan handoff is display-only and evidence-first."


def build_route_plan_panel(input_path: Path) -> MatrixRoutePlanPanelModel:
    """Build a non-interactive panel model from an existing route-plan.v1 JSON fixture."""

    view = build_route_plan_view(input_path)
    return MatrixRoutePlanPanelModel(
        schema_version="matrix-ui-route-plan-panel.v1",
        source_schema_version=view.source_schema_version,
        intent=view.intent,
        chosen_candidate_id=view.chosen_candidate_id,
        candidate_ranking=list(view.candidate_ranking),
        required_evidence_outputs=list(view.required_evidence_outputs),
        required_approval_gate=view.required_approval_gate,
        fail_closed=view.fail_closed,
        unknown_capabilities=list(view.unknown_capabilities),
        runtime_execution=False,
        dashboard_claim=False,
        shell_execution=False,
        destructive_command_path=False,
        non_execution_boundary=view.non_execution_boundary,
        panel_boundary=(
            "Display-only Textual-compatible panel model; no live UI route, runtime, "
            "adapter, shell, destructive command path, or dashboard is started."
        ),
        operator_snapshot_note=_operator_snapshot_note(view),
    )


def _render_list(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def render_route_plan_panel_text(panel: MatrixRoutePlanPanelModel) -> str:
    """Render deterministic panel text for tests and future UI attach points."""

    chosen = panel.chosen_candidate_id if panel.chosen_candidate_id is not None else "none"
    return "\n".join(
        [
            "Matrix UI Route Plan Panel Model",
            f"Schema: {panel.schema_version}",
            f"Source schema: {panel.source_schema_version}",
            f"Intent: {panel.intent}",
            f"Chosen candidate: {chosen}",
            f"Candidate ranking: {_render_list(panel.candidate_ranking)}",
            f"Evidence requirements: {_render_list(panel.required_evidence_outputs)}",
            f"Approval gate: {panel.required_approval_gate}",
            f"Fail closed: {'yes' if panel.fail_closed else 'no'}",
            f"Unknown capabilities: {_render_list(panel.unknown_capabilities)}",
            f"Runtime execution: {'yes' if panel.runtime_execution else 'no'}",
            f"Shell execution: {'yes' if panel.shell_execution else 'no'}",
            f"Destructive command path: {'yes' if panel.destructive_command_path else 'no'}",
            f"Production dashboard claim: {'yes' if panel.dashboard_claim else 'no'}",
            f"Non-execution boundary: {panel.non_execution_boundary}",
            f"Panel boundary: {panel.panel_boundary}",
            f"Operator snapshot: {panel.operator_snapshot_note}",
            "",
        ]
    )


class MatrixRoutePlanPanel(Static):
    """Non-interactive Textual widget shell for a route-plan panel model."""

    DEFAULT_CSS = """
    MatrixRoutePlanPanel {
        background: rgba(0, 15, 0, 0.9);
        color: #00FF00;
        border: round #00FF00;
        padding: 1;
    }
    """

    def __init__(self, panel_model: MatrixRoutePlanPanelModel, **kwargs) -> None:
        self.panel_model = panel_model
        self.renderable = render_route_plan_panel_text(panel_model)
        super().__init__(self.renderable, **kwargs)

    @classmethod
    def from_route_plan_file(cls, path: Path, **kwargs) -> MatrixRoutePlanPanel:
        """Construct a display-only panel widget from an existing route-plan file."""

        return cls(build_route_plan_panel(path), **kwargs)
