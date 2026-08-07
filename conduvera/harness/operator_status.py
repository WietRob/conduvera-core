"""Read-only operator workflow status for Matrix OS harness surfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from conduvera.evidence import EvidenceOperatorReport, build_operator_report
from conduvera.evidence.adapters.registry import AdapterDescriptor, list_adapter_descriptors
from conduvera.evidence.store import default_event_store_path
from conduvera.harness.gateway import (
    EditorSurfaceDescriptor,
    GatewayCapability,
    HarnessGatewayRegistry,
    RunnerDescriptor,
    ToolDescriptor,
)


@dataclass(frozen=True)
class OperatorSignals:
    """Action-oriented booleans derived from the latest evidence report."""

    approved_cr_present: bool
    agent_action_present: bool
    safety_block_present: bool
    failure_or_rule_proposal_present: bool
    traceability_gap_present: bool


@dataclass(frozen=True)
class HarnessOperatorStatus:
    """One read-only operator view over evidence, adapters, gateway, and UI metadata."""

    evidence_path: Path
    evidence: EvidenceOperatorReport
    adapters: tuple[AdapterDescriptor, ...]
    runners: tuple[RunnerDescriptor, ...]
    tools: tuple[ToolDescriptor, ...]
    capabilities: tuple[GatewayCapability, ...]
    editor_surfaces: tuple[EditorSurfaceDescriptor, ...]
    ui_attach_point: EditorSurfaceDescriptor
    signals: OperatorSignals
    next_step_hints: list[str] = field(default_factory=list)
    boundaries: dict[str, bool] = field(
        default_factory=lambda: {
            "read_only": True,
            "runtime_execution": False,
            "adapter_execution": False,
            "governance_mutation": False,
            "dashboard_runtime": False,
            "mcp_runtime": False,
        }
    )


def build_harness_operator_status(events_path: Path | None = None) -> HarnessOperatorStatus:
    """Build a read-only product-facing harness overview from existing contracts.

    ``events_path`` defaults to the local Matrix OS evidence store convention.
    The function only reads validated evidence events and declarative registries;
    it does not launch runners, call shells, register MCP tools, or mutate
    governance settings.
    """

    resolved_events_path = Path(events_path) if events_path is not None else default_event_store_path()
    evidence_report = build_operator_report(resolved_events_path)
    gateway = HarnessGatewayRegistry.default()
    ui_attach_point = gateway.get_editor_surface("matrix-ui-code-editor")
    signals = _signals(evidence_report)
    return HarnessOperatorStatus(
        evidence_path=resolved_events_path,
        evidence=evidence_report,
        adapters=list_adapter_descriptors(),
        runners=gateway.runners,
        tools=gateway.tools,
        capabilities=gateway.capabilities,
        editor_surfaces=gateway.editor_surfaces,
        ui_attach_point=ui_attach_point,
        signals=signals,
        next_step_hints=_next_step_hints(evidence_report),
    )


def render_harness_operator_status(status: HarnessOperatorStatus) -> str:
    """Render a terminal-readable harness operator status."""

    adapter_ids = ", ".join(adapter.adapter_id for adapter in status.adapters) or "none"
    lines = [
        "Matrix OS Harness Operator Status",
        f"Events: {status.evidence_path}",
        f"Read-only: {'yes' if status.boundaries['read_only'] else 'no'}",
        "Runners/tools/surfaces described, not executed",
        "No runtime execution; no adapter execution; no governance mutation; no MCP runtime.",
        "",
        f"Evidence report contract: {status.evidence.report_schema_version}",
        f"Evidence events: {status.evidence.total_events}",
        f"Evidence event types: {_format_counts(status.evidence.event_types)}",
        f"Evidence adapters observed: {_format_counts(status.evidence.adapters)}",
        "",
        f"Adapters: {adapter_ids}",
    ]
    lines.extend(
        f"- {adapter.adapter_id}: {adapter.execution_mode}, {adapter.production_status}"
        for adapter in status.adapters
    )
    lines.extend(["", "Harness runners:"])
    lines.extend(
        f"- {runner.name}: {runner.execution_status}, runtime_enabled={runner.runtime_enabled}"
        for runner in status.runners
    )
    lines.extend(["", "Harness tools:"])
    lines.extend(
        f"- {tool.name}: observe={tool.can_observe}, block={tool.can_block}, emit_evidence={tool.can_emit_evidence}, launch={tool.can_launch}"
        for tool in status.tools
    )
    lines.extend(
        [
            "",
            f"UI attach point: {status.ui_attach_point.surface_id}",
            f"- {status.ui_attach_point.name}",
            f"- future panels: {', '.join(status.ui_attach_point.future_attach_points)}",
            "",
            "Operator signals:",
            f"- approved CR present: {_yes_no(status.signals.approved_cr_present)}",
            f"- agent action present: {_yes_no(status.signals.agent_action_present)}",
            f"- safety block present: {_yes_no(status.signals.safety_block_present)}",
            f"- failure/rule proposal present: {_yes_no(status.signals.failure_or_rule_proposal_present)}",
            f"- traceability gap present: {_yes_no(status.signals.traceability_gap_present)}",
            "",
            "Next-step hints:",
        ]
    )
    lines.extend(f"- {hint}" for hint in status.next_step_hints)
    return "\n".join(lines).rstrip() + "\n"


def _signals(report: EvidenceOperatorReport) -> OperatorSignals:
    return OperatorSignals(
        approved_cr_present=any(item.get("status") == "approved" for item in report.change_requests),
        agent_action_present=bool(report.agent_actions),
        safety_block_present=bool(report.blocked_actions),
        failure_or_rule_proposal_present=bool(report.failures or report.rule_proposals),
        traceability_gap_present=bool(report.traceability_gaps),
    )


def _next_step_hints(report: EvidenceOperatorReport) -> list[str]:
    hints: list[str] = []
    approved = next((item for item in report.change_requests if item.get("status") == "approved"), None)
    if approved:
        hints.append(
            f"Approved CR {approved['change_request_id']} is present; inspect linked agent action before execution."
        )
    else:
        hints.append("No approved CR present; operator should request or inspect CR evidence before action.")

    if report.agent_actions:
        action = report.agent_actions[0]
        hints.append(
            f"Agent action {action['run_id']} by {action['agent_id']} is present; verify changed files and requirements."
        )
    else:
        hints.append("No agent action evidence present; keep runner surfaces descriptor-only.")

    if report.blocked_actions:
        blocked = report.blocked_actions[0]
        hints.append(
            f"Safety block present for {blocked['action']}; keep action blocked until explicit human review."
        )
    else:
        hints.append("No safety block present in this stream; continue read-only inspection.")

    if report.failures or report.rule_proposals:
        hints.append("Failure/rule proposal present; treat proposed rule as evidence only, not enforcement.")
    else:
        hints.append("No failure/rule proposal present; do not create governance changes from this status view.")

    if report.traceability_gaps:
        gap = report.traceability_gaps[0]
        hints.append(
            f"Traceability gap {gap['requirement_id']} missing {gap['missing_link']}; create or link verification evidence."
        )
    else:
        hints.append("No traceability gap present; preserve current evidence links.")
    return hints


def _format_counts(values: dict[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in values.items()) or "none"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
