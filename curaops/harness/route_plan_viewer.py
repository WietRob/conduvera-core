"""Read-only Matrix UI route-plan viewer stub.

This module consumes existing route-plan.v1 JSON artifacts and renders a display-only
operator view model. It does not plan, execute, launch, or adapt any runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MatrixUiRoutePlanView:
    """Display-only view model for a route-plan.v1 handoff artifact."""

    schema_version: str
    source_schema_version: str
    intent: str
    chosen_candidate_id: str | None
    candidate_ranking: list[str]
    required_evidence_outputs: list[str]
    required_approval_gate: str
    non_execution_boundary: str
    unknown_capabilities: list[str]
    fail_closed: bool
    execute_now: bool
    runtime_execution: bool
    dashboard_claim: bool
    display_boundary: str


def _require_route_plan_v1(payload: dict[str, Any], source: Path) -> None:
    schema_version = payload.get("schema_version")
    if schema_version != "route-plan.v1":
        raise ValueError(f"{source}: expected route-plan.v1, got {schema_version!r}")


def build_route_plan_view(input_path: Path) -> MatrixUiRoutePlanView:
    """Build a display-only Matrix UI route-plan view from an existing JSON artifact."""

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    _require_route_plan_v1(payload, input_path)

    candidates = payload.get("candidates", [])
    candidate_ranking = [candidate["candidate_id"] for candidate in candidates]
    intent = payload.get("intent", {})

    return MatrixUiRoutePlanView(
        schema_version="matrix-ui-route-plan-view.v1",
        source_schema_version=payload["schema_version"],
        intent=intent.get("text", ""),
        chosen_candidate_id=payload.get("chosen_candidate_id"),
        candidate_ranking=candidate_ranking,
        required_evidence_outputs=list(payload.get("required_evidence_outputs", [])),
        required_approval_gate=payload.get("required_approval_gate", ""),
        non_execution_boundary=payload.get("non_execution_boundary", ""),
        unknown_capabilities=list(payload.get("unknown_capabilities", [])),
        fail_closed=bool(payload.get("fail_closed", False)),
        execute_now=False,
        runtime_execution=False,
        dashboard_claim=False,
        display_boundary="Display-only view over an existing route-plan JSON artifact; no live runtime, adapter, shell, or dashboard is started.",
    )


def _render_list(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def render_route_plan_view(view: MatrixUiRoutePlanView) -> str:
    """Render the Matrix UI route-plan view stub for terminal/operator inspection."""

    chosen = view.chosen_candidate_id if view.chosen_candidate_id is not None else "none"
    return "\n".join(
        [
            "Matrix UI Route Plan Viewer Stub",
            f"Schema: {view.schema_version}",
            f"Source schema: {view.source_schema_version}",
            f"Intent: {view.intent}",
            f"Chosen candidate: {chosen}",
            f"Candidate ranking: {_render_list(view.candidate_ranking)}",
            f"Evidence requirements: {_render_list(view.required_evidence_outputs)}",
            f"Approval gate: {view.required_approval_gate}",
            f"Fail closed: {'yes' if view.fail_closed else 'no'}",
            f"Unknown capabilities: {_render_list(view.unknown_capabilities)}",
            f"Execute now: {'yes' if view.execute_now else 'no'}",
            f"Runtime execution: {'yes' if view.runtime_execution else 'no'}",
            f"Production dashboard claim: {'yes' if view.dashboard_claim else 'no'}",
            f"Non-execution boundary: {view.non_execution_boundary}",
            f"Display boundary: {view.display_boundary}",
            "",
        ]
    )
