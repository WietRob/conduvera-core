"""Operator-readable reports over Matrix OS evidence event streams."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from curaops.evidence.contract import ValidationError
from curaops.evidence.store import read_event_stream

ReportFormat = Literal["text", "markdown", "json"]


@dataclass(frozen=True)
class EvidenceOperatorReport:
    """Deterministic operator report derived from validated evidence events."""

    total_events: int
    event_types: dict[str, int]
    producers: dict[str, int]
    subjects: dict[str, int]
    adapters: dict[str, int]
    agent_actions: list[dict[str, Any]] = field(default_factory=list)
    blocked_actions: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    rule_proposals: list[dict[str, Any]] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    traceability_gaps: list[dict[str, Any]] = field(default_factory=list)
    boundaries: dict[str, bool] = field(
        default_factory=lambda: {
            "external_runtime_required": False,
            "automatic_rule_enforcement": False,
            "production_audit_retention": False,
            "dashboard_runtime": False,
        }
    )

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-serializable report dictionary."""

        return asdict(self)


def build_operator_report(events_path: Path) -> EvidenceOperatorReport:
    """Build an operator-readable report from a Matrix OS EventEnvelope JSONL stream.

    The input stream is validated by the evidence backbone reader. Invalid JSON,
    unsupported event types, missing hashes, or malformed envelopes raise
    ``ValidationError`` and fail closed.
    """

    events_path = Path(events_path)
    if not events_path.exists():
        raise ValidationError(f"missing file: {events_path}")
    events = sorted(list(read_event_stream(events_path)), key=lambda event: (event.occurred_at, event.event_id))
    requirements: set[str] = set()

    for event in events:
        requirements.update(_extract_requirements(event.payload))
        for reference in event.references or []:
            if isinstance(reference, dict) and reference.get("kind") == "requirement" and reference.get("id"):
                requirements.add(str(reference["id"]))

    return EvidenceOperatorReport(
        total_events=len(events),
        event_types=_count(event.event_type for event in events),
        producers=_count(event.producer["name"] for event in events),
        subjects=_count(event.subject["kind"] for event in events),
        adapters=_count(_adapter_id(event.producer) for event in events),
        agent_actions=_agent_actions(events),
        blocked_actions=_blocked_actions(events),
        failures=_failures(events),
        rule_proposals=_rule_proposals(events),
        requirements=sorted(requirements),
        traceability_gaps=_traceability_gaps(events),
    )


def render_operator_report(report: EvidenceOperatorReport, format: ReportFormat = "text") -> str:
    """Render an operator report as text, Markdown, or JSON."""

    if format == "json":
        return json.dumps(report.to_dict(), sort_keys=True, indent=2)
    if format == "markdown":
        return _render_markdown(report)
    if format == "text":
        return _render_text(report)
    raise ValueError(f"unsupported evidence report format: {format}")


def _count(values) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _adapter_id(producer: dict[str, Any]) -> str:
    adapter = producer.get("adapter")
    if isinstance(adapter, str) and adapter:
        return adapter
    return "native"


def _extract_requirements(payload: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for key in ("requirement_refs", "requirements"):
        refs = payload.get(key)
        if isinstance(refs, list):
            values.update(str(ref) for ref in refs if ref)
    requirement_id = payload.get("requirement_id")
    if requirement_id:
        values.add(str(requirement_id))
    return values


def _agent_actions(events) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for event in events:
        if event.event_type != "accountable_change.evidence.generated":
            continue
        payload = event.payload
        actions.append(
            {
                "agent_id": str(payload.get("agent_id", "unknown")),
                "run_id": str(payload.get("run_id") or event.run_id or "unknown"),
                "change_request_id": str(payload.get("change_request_id") or event.correlation_id or "unknown"),
                "changed_files": list(payload.get("changed_files") or []),
                "requirements": sorted(_extract_requirements(payload)),
                "adapter": _adapter_id(event.producer),
            }
        )
    return actions


def _blocked_actions(events) -> list[dict[str, Any]]:
    blocked: list[dict[str, Any]] = []
    for event in events:
        if event.event_type != "safety_guard.action.blocked":
            continue
        action = event.payload.get("action") if isinstance(event.payload.get("action"), dict) else {}
        blocked.append(
            {
                "action": str(action.get("command") or action.get("path") or "unknown"),
                "action_kind": str(action.get("kind") or event.subject.get("action_kind") or "unknown"),
                "path": str(action.get("path") or ""),
                "reason": str(event.payload.get("reason") or "unknown"),
                "adapter": _adapter_id(event.producer),
            }
        )
    return blocked


def _failures(events) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for event in events:
        if event.event_type != "failure.observed":
            continue
        failure = event.payload.get("failure") if isinstance(event.payload.get("failure"), dict) else {}
        failures.append(
            {
                "kind": str(failure.get("kind") or event.subject.get("failure_kind") or "unknown"),
                "signature": str(failure.get("signature") or event.subject.get("signature") or "unknown"),
                "summary": str(failure.get("summary") or "unknown"),
                "adapter": _adapter_id(event.producer),
            }
        )
    return failures


def _rule_proposals(events) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for event in events:
        if event.event_type != "rule.proposed":
            continue
        proposal = event.payload.get("proposal") if isinstance(event.payload.get("proposal"), dict) else {}
        proposals.append(
            {
                "rule_id": str(proposal.get("rule_id") or event.subject.get("rule_id") or "unknown"),
                "title": str(proposal.get("title") or "unknown"),
                "enforced": bool(event.payload.get("enforced", False)),
                "policy_action": str(event.payload.get("policy_action") or "none"),
                "adapter": _adapter_id(event.producer),
            }
        )
    return proposals


def _traceability_gaps(events) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for event in events:
        if event.event_type != "aspice.check.completed":
            continue
        missing_link = event.payload.get("missing_link")
        if not missing_link:
            continue
        gaps.append(
            {
                "requirement_id": str(event.payload.get("requirement_id") or event.subject.get("id") or "unknown"),
                "missing_link": str(missing_link),
                "source_file": str(event.payload.get("source_file") or "unknown"),
            }
        )
    return gaps


def _operator_answers(report: EvidenceOperatorReport) -> list[tuple[str, str]]:
    agent_answer = "No accountable agent action found."
    if report.agent_actions:
        action = report.agent_actions[0]
        agent_answer = (
            f"{action['agent_id']} run {action['run_id']} changed "
            f"{', '.join(action['changed_files']) or 'unknown files'} under {action['change_request_id']}."
        )

    safety_answer = "No blocked risky action found."
    if report.blocked_actions:
        blocked = report.blocked_actions[0]
        safety_answer = f"{blocked['action']} was blocked because {blocked['reason']}."

    failure_answer = "No failure/rule-proposal pair found."
    if report.failures and report.rule_proposals:
        failure = report.failures[0]
        proposal = report.rule_proposals[0]
        enforcement = "not enforced" if not proposal["enforced"] else "enforced"
        failure_answer = f"{failure['summary']}; proposed {proposal['rule_id']} ({enforcement})."

    trace_answer = "No traceability gap found."
    if report.traceability_gaps:
        gap = report.traceability_gaps[0]
        trace_answer = f"{gap['requirement_id']} is missing {gap['missing_link']} in {gap['source_file']}."

    adapters = ", ".join(f"{adapter}={count}" for adapter, count in report.adapters.items()) or "none"
    return [
        ("Which agent changed what under which CR?", agent_answer),
        ("What risky action was blocked and why?", safety_answer),
        ("What failure was observed and what rule was proposed?", failure_answer),
        ("Which requirement or traceability object is relevant?", trace_answer),
        ("Which adapter produced the evidence?", adapters),
    ]


def _render_text(report: EvidenceOperatorReport) -> str:
    lines = [
        "Matrix OS Evidence Operator Report",
        f"Total events: {report.total_events}",
        "",
        "Counts by event type:",
    ]
    lines.extend(f"- {key}: {value}" for key, value in report.event_types.items())
    lines.append("Counts by producer:")
    lines.extend(f"- {key}: {value}" for key, value in report.producers.items())
    lines.append("Counts by subject:")
    lines.extend(f"- {key}: {value}" for key, value in report.subjects.items())
    lines.append("Counts by adapter:")
    lines.extend(f"- {key}: {value}" for key, value in report.adapters.items())
    lines.append("")
    lines.append("Operator answers:")
    lines.extend(f"- {question} {answer}" for question, answer in _operator_answers(report))
    lines.append("")
    lines.append("Agent actions:")
    lines.extend(f"- {item['agent_id']} {item['run_id']} {item['change_request_id']} {item['changed_files']}" for item in report.agent_actions)
    lines.append("Blocked actions:")
    lines.extend(f"- {item['action']} blocked because {item['reason']}" for item in report.blocked_actions)
    lines.append("Failures:")
    lines.extend(f"- {item['summary']}" for item in report.failures)
    lines.append("Rule proposals:")
    lines.extend(
        f"- {item['rule_id']}: {item['title']} (not enforced, policy_action={item['policy_action']})"
        if not item["enforced"]
        else f"- {item['rule_id']}: {item['title']} (enforced)"
        for item in report.rule_proposals
    )
    lines.append("Traceability gaps:")
    lines.extend(f"- {item['requirement_id']}: missing {item['missing_link']}" for item in report.traceability_gaps)
    lines.append("Boundaries: no external runtime, no dashboard runtime, no production audit retention, no automatic rule enforcement.")
    return "\n".join(lines).rstrip() + "\n"


def _render_markdown(report: EvidenceOperatorReport) -> str:
    lines = [
        "# Matrix OS Evidence Operator Report",
        "",
        f"Total events: {report.total_events}",
        "",
        "## Operator questions",
        "",
        "| Question | Answer |",
        "|---|---|",
    ]
    lines.extend(f"| {question} | {answer} |" for question, answer in _operator_answers(report))
    lines.extend(
        [
            "",
            "## Counts",
            "",
            "| Dimension | Value | Count |",
            "|---|---|---:|",
        ]
    )
    for dimension, values in (
        ("event_type", report.event_types),
        ("producer", report.producers),
        ("subject", report.subjects),
        ("adapter", report.adapters),
    ):
        lines.extend(f"| {dimension} | {key} | {value} |" for key, value in values.items())
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- No external runtime execution.",
            "- No dashboard runtime.",
            "- No production audit-retention claim.",
            "- Proposed rules remain evidence only and are not enforced.",
        ]
    )
    return "\n".join(lines) + "\n"
