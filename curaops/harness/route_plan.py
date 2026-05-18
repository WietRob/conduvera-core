"""Descriptor-only dry-run route planning for Matrix OS Harness Gateway.

This module translates an operator intent into a route plan. It never launches
runners, shells, Pi Agent Harness, Hermes, OpenCode, MCP, editor integrations, or
external evidence producers. Output is a planning/evidence contract only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from curaops.harness.gateway import HarnessGatewayRegistry


@dataclass(frozen=True)
class OperatorIntent:
    """Operator request text plus optional metadata used for dry-run routing."""

    text: str
    actor: str = "operator"
    correlation_id: str | None = None


@dataclass(frozen=True)
class CapabilityMatch:
    """Why a candidate matched a dry-run route-plan capability."""

    capability_id: str
    matched: bool
    reason: str


@dataclass(frozen=True)
class RouteCandidate:
    """Descriptor-only route candidate. It is never executed by this planner."""

    candidate_id: str
    name: str
    candidate_type: str
    rank: int
    runtime_enabled: bool
    selection_reason: str
    capability_matches: tuple[CapabilityMatch, ...]
    what_would_execute_later: str
    not_executed_now: str


@dataclass(frozen=True)
class RoutePlanStep:
    """Evidence/planning step in a dry-run route plan."""

    step_id: str
    description: str
    expected_output: str
    execute_now: bool = False


@dataclass(frozen=True)
class RoutePlan:
    """Complete dry-run route plan for an operator intent."""

    intent: OperatorIntent
    chosen_candidate_id: str | None
    candidates: tuple[RouteCandidate, ...]
    steps: tuple[RoutePlanStep, ...]
    required_evidence_outputs: tuple[str, ...]
    required_approval_gate: str
    unknown_capabilities: tuple[str, ...] = ()
    fail_closed: bool = False
    execute_now: bool = False
    non_execution_boundary: str = (
        "No runner, shell command, editor integration, MCP server, Pi Agent Harness, "
        "Hermes, OpenCode, or evidence adapter is executed by this dry-run planner."
    )


def _match(capability_id: str, reason: str, *, matched: bool = True) -> CapabilityMatch:
    return CapabilityMatch(capability_id=capability_id, matched=matched, reason=reason)


def _runner_candidate(candidate_id: str, rank: int, reason: str) -> RouteCandidate:
    runner = HarnessGatewayRegistry.default().get_runner(candidate_id)
    return RouteCandidate(
        candidate_id=runner.runner_id,
        name=runner.name,
        candidate_type="runner-descriptor",
        rank=rank,
        runtime_enabled=runner.runtime_enabled,
        selection_reason=reason,
        capability_matches=(
            _match("route-planning", reason),
            _match("evidence-plan", "would require translated EventEnvelope evidence before future execution"),
        ),
        what_would_execute_later=f"Future reviewed adapter could route to {runner.name} after CCC/AAL/safety gates.",
        not_executed_now=f"{runner.name} is descriptor-only and not executed by Matrix OS now.",
    )


def _tool_candidate(candidate_id: str, rank: int, reason: str) -> RouteCandidate:
    tool = HarnessGatewayRegistry.default().get_tool(candidate_id)
    return RouteCandidate(
        candidate_id=tool.tool_id,
        name=tool.name,
        candidate_type="evidence-tool-descriptor",
        rank=rank,
        runtime_enabled=False,
        selection_reason=reason,
        capability_matches=(
            _match("convert_evidence", "translation-only evidence path"),
            _match("approve_block", reason),
        ),
        what_would_execute_later=f"Future workflow could consume {tool.name} output after explicit producer run outside this planner.",
        not_executed_now=f"{tool.name} is not executed or launched; only evidence requirements are planned.",
    )


def _surface_candidate(candidate_id: str, rank: int, reason: str) -> RouteCandidate:
    surface = HarnessGatewayRegistry.default().get_editor_surface(candidate_id)
    return RouteCandidate(
        candidate_id=surface.surface_id,
        name=surface.name,
        candidate_type="display-surface-descriptor",
        rank=rank,
        runtime_enabled=False,
        selection_reason=reason,
        capability_matches=(
            _match("display_attach", "display/attach-only surface"),
            _match("observe", "read-only operator view over existing evidence/status"),
        ),
        what_would_execute_later="Future UI could display route/evidence status from Matrix OS APIs.",
        not_executed_now=f"{surface.name} is not opened, launched, or claimed as a production dashboard.",
    )


def _plan_code_change(intent: OperatorIntent) -> RoutePlan:
    candidates = (
        _runner_candidate("hermes", 1, "best descriptor match for agent task orchestration intent"),
        _runner_candidate("opencode", 2, "coding-agent descriptor also matches code-change workflow"),
        _runner_candidate("pi-agent-harness", 3, "Pi concepts are descriptor-only future backend candidates"),
        _tool_candidate("agent-evidence-plane", 4, "agent evidence conversion would be required after a future run"),
    )
    return RoutePlan(
        intent=intent,
        chosen_candidate_id="hermes",
        candidates=candidates,
        steps=(
            RoutePlanStep("classify-intent", "Classify as AI-assisted code-change route", "route.intent.classified"),
            RoutePlanStep("require-approval", "Require CCC/AAL approval before future execution", "approval.required"),
            RoutePlanStep("plan-evidence", "Plan accountable change and agent-run evidence outputs", "evidence.plan"),
        ),
        required_evidence_outputs=(
            "change_request.evidence.generated",
            "accountable_change.evidence.generated",
            "agent.run.completed",
        ),
        required_approval_gate="CCC/AAL approval before any future execution",
    )


def _plan_dangerous_file_operation(intent: OperatorIntent) -> RoutePlan:
    return RoutePlan(
        intent=intent,
        chosen_candidate_id="safety-guard",
        candidates=(
            _tool_candidate("safety-guard", 1, "dangerous/destructive operation requires safety evidence first"),
            _runner_candidate("local-shell", 2, "future shell boundary remains blocked until safety and approval gates pass"),
        ),
        steps=(
            RoutePlanStep("classify-risk", "Classify destructive or dangerous file operation", "risk.classified"),
            RoutePlanStep("safety-evidence-translation", "Require Safety Guard translated evidence", "safety_guard.action.blocked"),
            RoutePlanStep("block-execution", "Block destructive execution in dry-run", "execution.blocked"),
        ),
        required_evidence_outputs=("safety_guard.action.blocked",),
        required_approval_gate="Safety Guard evidence review before any destructive action",
        non_execution_boundary="No shell command, file deletion, or external tool is executed by the dry-run planner.",
    )


def _plan_failed_run(intent: OperatorIntent) -> RoutePlan:
    return RoutePlan(
        intent=intent,
        chosen_candidate_id="failure-driven-loop",
        candidates=(
            _tool_candidate("failure-driven-loop", 1, "failed run review maps to failure-loop evidence and rule proposal"),
            _tool_candidate("agent-evidence-plane", 2, "agent-run evidence may be needed as input context"),
        ),
        steps=(
            RoutePlanStep("collect-failure", "Plan failure evidence review", "failure.observed"),
            RoutePlanStep("propose-rule", "Plan non-enforced rule proposal", "rule.proposed evidence-only"),
        ),
        required_evidence_outputs=("failure.observed", "rule.proposed"),
        required_approval_gate="Human review before any rule adoption or enforcement",
    )


def _plan_ui_view(intent: OperatorIntent) -> RoutePlan:
    return RoutePlan(
        intent=intent,
        chosen_candidate_id="matrix-ui-code-editor",
        candidates=(
            _surface_candidate("matrix-ui-code-editor", 1, "original Matrix UI/editor surface can display operator route state"),
            _surface_candidate("zed-mcp-future", 2, "future external editor surface remains descriptor-only"),
        ),
        steps=(
            RoutePlanStep("prepare-view", "Plan read-only UI/status view", "harness.status.view"),
            RoutePlanStep("preserve-ui", "Preserve original Matrix UI/editor surfaces", "ui.surface.preserved"),
        ),
        required_evidence_outputs=("harness.status.view",),
        required_approval_gate="No execution approval requested for display-only dry-run",
        non_execution_boundary="Display/attach-only route; original Matrix UI preserved; no production dashboard claim.",
    )


def _plan_evidence_conversion(intent: OperatorIntent) -> RoutePlan:
    return RoutePlan(
        intent=intent,
        chosen_candidate_id="agent-evidence-plane",
        candidates=(
            _tool_candidate("agent-evidence-plane", 1, "external evidence conversion request"),
            _tool_candidate("safety-guard", 2, "safety evidence conversion candidate"),
            _tool_candidate("failure-driven-loop", 3, "failure evidence conversion candidate"),
        ),
        steps=(RoutePlanStep("convert-only", "Plan conversion-only adapter path", "EventEnvelope conversion plan"),),
        required_evidence_outputs=("EventEnvelope",),
        required_approval_gate="Human review for unsupported producer schemas",
    )


def _fail_closed(intent: OperatorIntent) -> RoutePlan:
    return RoutePlan(
        intent=intent,
        chosen_candidate_id=None,
        candidates=(),
        steps=(RoutePlanStep("fail-closed", "Unknown operator intent; require human route decision", "human.decision.required"),),
        required_evidence_outputs=(),
        required_approval_gate="Human route decision required",
        unknown_capabilities=("intent.classification",),
        fail_closed=True,
    )


def plan_route(intent: OperatorIntent | str) -> RoutePlan:
    """Return a non-executing dry-run route plan for an operator intent."""

    operator_intent = OperatorIntent(intent) if isinstance(intent, str) else intent
    text = operator_intent.text.strip().lower()

    if any(term in text for term in ("code change", "agent task", "evidence capture", "ai-assisted")):
        return _plan_code_change(operator_intent)
    if any(term in text for term in ("dangerous", "delete", "destructive", "rm ", "file operation")):
        return _plan_dangerous_file_operation(operator_intent)
    if any(term in text for term in ("failed agent", "failed run", "failure", "propose rule")):
        return _plan_failed_run(operator_intent)
    if any(term in text for term in ("ui view", "operator wants ui", "harness status", "display")):
        return _plan_ui_view(operator_intent)
    if any(term in text for term in ("convert external evidence", "evidence conversion", "external evidence")):
        return _plan_evidence_conversion(operator_intent)
    return _fail_closed(operator_intent)


def route_plan_to_dict(plan: RoutePlan) -> dict[str, Any]:
    """Return a stable machine-readable dry-run route-plan contract."""

    return {
        "schema_version": "route-plan.v1",
        "intent": {
            "text": plan.intent.text,
            "actor": plan.intent.actor,
            "correlation_id": plan.intent.correlation_id,
        },
        "chosen_candidate_id": plan.chosen_candidate_id,
        "execute_now": plan.execute_now,
        "fail_closed": plan.fail_closed,
        "required_approval_gate": plan.required_approval_gate,
        "non_execution_boundary": plan.non_execution_boundary,
        "required_evidence_outputs": list(plan.required_evidence_outputs),
        "unknown_capabilities": list(plan.unknown_capabilities),
        "candidates": [
            {
                "candidate_id": candidate.candidate_id,
                "name": candidate.name,
                "candidate_type": candidate.candidate_type,
                "rank": candidate.rank,
                "runtime_enabled": candidate.runtime_enabled,
                "selection_reason": candidate.selection_reason,
                "capability_matches": [
                    {
                        "capability_id": match.capability_id,
                        "matched": match.matched,
                        "reason": match.reason,
                    }
                    for match in candidate.capability_matches
                ],
                "what_would_execute_later": candidate.what_would_execute_later,
                "not_executed_now": candidate.not_executed_now,
            }
            for candidate in plan.candidates
        ],
        "steps": [
            {
                "step_id": step.step_id,
                "description": step.description,
                "expected_output": step.expected_output,
                "execute_now": step.execute_now,
            }
            for step in plan.steps
        ],
    }


def render_route_plan(plan: RoutePlan) -> str:
    """Render a route plan as stable terminal-readable text."""

    lines = [
        "DRY-RUN ROUTE PLAN",
        f"intent: {plan.intent.text}",
        f"execute_now: {str(plan.execute_now).lower()}",
        f"fail_closed: {str(plan.fail_closed).lower()}",
        f"chosen_candidate: {plan.chosen_candidate_id or 'NONE'}",
        f"required_approval_gate: {plan.required_approval_gate}",
        f"non_execution_boundary: {plan.non_execution_boundary}",
        "required_evidence_outputs:",
    ]
    lines.extend(f"- {event_type}" for event_type in plan.required_evidence_outputs)
    if plan.unknown_capabilities:
        lines.append("unknown_capabilities:")
        lines.extend(f"- {capability}" for capability in plan.unknown_capabilities)
    lines.append("candidates:")
    if not plan.candidates:
        lines.append("- NONE (fail closed; human route decision required)")
    for candidate in plan.candidates:
        lines.extend(
            [
                f"- id: {candidate.candidate_id}",
                f"  rank: {candidate.rank}",
                f"  type: {candidate.candidate_type}",
                f"  runtime_enabled: {str(candidate.runtime_enabled).lower()}",
                f"  why_selected: {candidate.selection_reason}",
                f"  what_would_execute_later: {candidate.what_would_execute_later}",
                f"  what_is_not_executed_now: {candidate.not_executed_now}",
            ]
        )
    lines.append("steps:")
    for step in plan.steps:
        lines.extend(
            [
                f"- id: {step.step_id}",
                f"  execute_now: {str(step.execute_now).lower()}",
                f"  description: {step.description}",
                f"  expected_output: {step.expected_output}",
            ]
        )
    return "\n".join(lines) + "\n"
