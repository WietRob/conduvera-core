"""Thin adapter from agent-evidence-plane JSONL events to Matrix OS events.

This module intentionally does not import or vendor the external
agent-evidence-plane package. It validates the compatible public JSON event
shape and translates it into the Matrix OS ``EventEnvelope`` contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from curaops.evidence import EventEnvelope, EvidenceStore, ValidationError

AGENT_EVIDENCE_PLANE_SCHEMA_VERSION = "0.1.0"
AGENT_EVIDENCE_PLANE_EVENT_TYPES = {
    "agent.run.started",
    "agent.run.completed",
    "agent.run.failed",
    "failure.observed",
}
ADAPTER_NAME = "matrix-os.agent-evidence-plane"


def translate_agent_evidence_plane_event(data: dict[str, Any]) -> EventEnvelope:
    """Translate one compatible agent-evidence-plane event into Matrix OS.

    Unsupported or malformed external events fail closed with ``ValidationError``.
    The original external payload is nested under ``payload.external_payload`` so
    Matrix OS remains canonical while preserving source detail for audit/debug.
    """

    _validate_agent_evidence_plane_event(data)
    external_event_id = data["event_id"]
    external_event_type = data["event_type"]
    external_producer = dict(data["producer"])
    producer = {
        **external_producer,
        "adapter": ADAPTER_NAME,
        "external_schema_version": data["schema_version"],
    }
    subject = dict(data["subject"])
    payload = {
        "external_event_id": external_event_id,
        "external_event_type": external_event_type,
        "external_schema_version": data["schema_version"],
        "external_payload": data["payload"],
    }
    if "evidence" in data:
        payload["external_evidence"] = data["evidence"]

    return EventEnvelope.create(
        event_type=external_event_type,
        event_id=f"mxev_aep_{external_event_id}",
        occurred_at=data["occurred_at"],
        producer=producer,
        subject=subject,
        severity=data.get("severity", "info"),
        correlation_id=data.get("correlation_id"),
        run_id=data.get("run_id"),
        references=_extract_references(data),
        links=_translate_links(data.get("links")),
        payload=payload,
    )


def convert_agent_evidence_plane_jsonl(input_path: str | Path, output_path: str | Path) -> int:
    """Convert an agent-evidence-plane JSONL stream into Matrix OS JSONL."""

    translated: list[EventEnvelope] = []
    try:
        with Path(input_path).open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                    translated.append(translate_agent_evidence_plane_event(raw))
                except json.JSONDecodeError as exc:
                    raise ValidationError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
                except ValidationError as exc:
                    raise ValidationError(f"line {line_number}: {exc}") from exc
    except OSError as exc:
        raise ValidationError(str(exc)) from exc

    store = EvidenceStore(output_path)
    for event in translated:
        store.append(event)
    return len(translated)


def _validate_agent_evidence_plane_event(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValidationError("agent-evidence-plane event must be an object")
    for field in ("schema_version", "event_id", "event_type", "occurred_at", "producer", "subject", "payload"):
        if field not in data:
            raise ValidationError(f"missing required field: {field}")
    if data["schema_version"] != AGENT_EVIDENCE_PLANE_SCHEMA_VERSION:
        raise ValidationError(f"unsupported agent-evidence-plane schema_version: {data['schema_version']}")
    if not isinstance(data["event_id"], str) or not data["event_id"].startswith("evt_"):
        raise ValidationError("agent-evidence-plane event_id must start with evt_")
    if data["event_type"] not in AGENT_EVIDENCE_PLANE_EVENT_TYPES:
        raise ValidationError(f"unsupported agent-evidence-plane event_type: {data['event_type']}")
    if not isinstance(data["occurred_at"], str) or not data["occurred_at"].endswith("Z"):
        raise ValidationError("occurred_at must be UTC RFC3339 with Z suffix")
    if not isinstance(data["producer"], dict) or not data["producer"].get("name"):
        raise ValidationError("missing required field: producer.name")
    if not isinstance(data["subject"], dict) or not data["subject"].get("kind"):
        raise ValidationError("missing required field: subject.kind")
    if not isinstance(data["payload"], dict):
        raise ValidationError("payload must be an object")
    severity = data.get("severity", "info")
    if severity not in {"debug", "info", "warning", "error", "critical"}:
        raise ValidationError(f"unsupported severity: {severity}")
    links = data.get("links")
    if links is not None and not isinstance(links, list):
        raise ValidationError("links must be a list")
    evidence = data.get("evidence")
    if evidence is not None and not isinstance(evidence, dict):
        raise ValidationError("evidence must be an object")


def _extract_references(data: dict[str, Any]) -> list[dict[str, Any]] | None:
    evidence = data.get("evidence")
    if not isinstance(evidence, dict):
        return None
    path = evidence.get("artifact_path") or evidence.get("path")
    if not isinstance(path, str) or not path:
        return None
    reference = {
        "kind": "agent-evidence-plane.evidence",
        "path": path,
        "external_event_id": data["event_id"],
    }
    sha256 = evidence.get("sha256")
    if isinstance(sha256, str) and sha256:
        reference["sha256"] = sha256
    return [reference]


def _translate_links(links: object) -> list[dict[str, Any]] | None:
    if not links:
        return None
    translated: list[dict[str, Any]] = []
    for link in links:
        if not isinstance(link, dict):
            raise ValidationError("links must contain objects")
        rel = link.get("rel")
        event_id = link.get("event_id")
        if not isinstance(rel, str) or not rel:
            raise ValidationError("links.rel is required")
        if not isinstance(event_id, str) or not event_id.startswith("evt_"):
            raise ValidationError("links.event_id must start with evt_")
        translated.append({"rel": f"external:{rel}", "external_event_id": event_id})
    return translated
