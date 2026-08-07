"""Read-only Matrix UI route-plan viewer stub.

This module consumes existing route-plan.v1 JSON artifacts and renders a display-only
operator view model. It does not plan, execute, launch, or adapt any runtime.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
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

    required_fields = {
        "intent",
        "chosen_candidate_id",
        "execute_now",
        "fail_closed",
        "required_approval_gate",
        "non_execution_boundary",
        "required_evidence_outputs",
        "unknown_capabilities",
        "candidates",
        "steps",
    }
    missing_fields = sorted(required_fields - payload.keys())
    if missing_fields:
        raise ValueError(f"{source}: missing route-plan.v1 fields: {', '.join(missing_fields)}")
    if payload["execute_now"] is not False:
        raise ValueError(f"{source}: route-plan.v1 execute_now must be false")
    if not isinstance(payload["intent"], dict) or not isinstance(payload["intent"].get("text"), str):
        raise ValueError(f"{source}: route-plan.v1 intent.text must be present")
    if not isinstance(payload["required_approval_gate"], str) or not payload["required_approval_gate"]:
        raise ValueError(f"{source}: route-plan.v1 required_approval_gate must be present")
    if not isinstance(payload["non_execution_boundary"], str) or not payload["non_execution_boundary"]:
        raise ValueError(f"{source}: route-plan.v1 non_execution_boundary must be present")
    if not isinstance(payload["candidates"], list):
        raise ValueError(f"{source}: route-plan.v1 candidates must be a list")
    if not isinstance(payload["steps"], list):
        raise ValueError(f"{source}: route-plan.v1 steps must be a list")
    for index, candidate in enumerate(payload["candidates"]):
        if not isinstance(candidate, dict):
            raise ValueError(f"{source}: route-plan.v1 candidate {index} must be an object")
        if not isinstance(candidate.get("candidate_id"), str):
            raise ValueError(f"{source}: route-plan.v1 candidate {index} candidate_id must be present")
        if candidate.get("runtime_enabled") is not False:
            raise ValueError(f"{source}: route-plan.v1 candidate {candidate.get('candidate_id')} runtime_enabled must be false")
    for index, step in enumerate(payload["steps"]):
        if not isinstance(step, dict):
            raise ValueError(f"{source}: route-plan.v1 step {index} must be an object")
        if step.get("execute_now") is not False:
            raise ValueError(f"{source}: route-plan.v1 step {step.get('step_id', index)} execute_now must be false")


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


def _operator_snapshot_note(view: MatrixUiRoutePlanView) -> str:
    if view.chosen_candidate_id == "failure-driven-loop":
        return "Operator snapshot: failed-run review; rule proposal is evidence-only and is not enforced."
    if view.chosen_candidate_id == "matrix-ui-code-editor":
        return "Operator snapshot: future UI handoff boundary; display-only Matrix UI/editor surface, not a live panel."
    if view.chosen_candidate_id == "safety-guard":
        return "Operator snapshot: destructive action boundary; safety evidence is required before any future action."
    if view.fail_closed:
        return "Operator snapshot: fail-closed; human route decision required before any future action."
    return "Operator snapshot: route-plan handoff is display-only and evidence-first."


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
            _operator_snapshot_note(view),
            "",
        ]
    )
