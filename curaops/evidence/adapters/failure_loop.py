"""Thin adapter from failure-driven-loop result JSONL to Matrix OS events.

This module intentionally does not execute failure-driven-loop commands or
apply/enforce proposed rules. It translates already-produced failure-loop
result objects into Matrix OS ``EventEnvelope`` evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from curaops.evidence import EventEnvelope, EvidenceStore, ValidationError

FAILURE_LOOP_SCHEMA_VERSION = "failure-loop.result.v1"
FAILURE_LOOP_EVENT_TYPES = {"failure.observed", "rule.proposed"}
SUPPORTED_FAILURE_KINDS = {
    "test_failure",
    "lint_failure",
    "typecheck_failure",
    "ci_failure",
    "traceability_failure",
    "naming_failure",
}
SUPPORTED_RECOMMENDATION_TYPES = {"rule_proposal"}
ADAPTER_NAME = "matrix-os.failure-loop"


def translate_failure_loop_result(data: dict[str, Any]) -> EventEnvelope | list[EventEnvelope]:
    """Translate one failure-loop result dictionary into Matrix OS evidence.

    The first returned event is always ``failure.observed``. If a supported
    recommendation is present, a second ``rule.proposed`` evidence event is
    returned. Proposed rules are never enforced by this adapter.
    """

    _validate_failure_loop_result(data)
    failure = data["failure"]
    result_id = data["result_id"]
    producer = {
        **dict(data["source"]),
        "adapter": ADAPTER_NAME,
        "external_schema_version": data["schema_version"],
    }
    references = _extract_references(data)
    recommendation = data.get("recommendation")
    base_payload = {
        "external_result_id": result_id,
        "external_schema_version": data["schema_version"],
        "failure": dict(failure),
        "recommendation": dict(recommendation) if isinstance(recommendation, dict) else None,
        "enforced": False,
        "policy_action": "none",
    }
    if data.get("metadata") is not None:
        base_payload["metadata"] = data["metadata"]

    failure_event = EventEnvelope.create(
        event_type="failure.observed",
        event_id=f"mxev_fl_{result_id}_failure",
        occurred_at=data["observed_at"],
        producer=producer,
        subject={
            "kind": "failure_loop_failure",
            "failure_kind": failure["kind"],
            "signature": failure["signature"],
        },
        severity=data.get("severity", "warning"),
        correlation_id=data.get("correlation_id") or result_id,
        run_id=data.get("run_id"),
        references=references,
        payload=base_payload,
    )

    if not isinstance(recommendation, dict):
        return failure_event

    rule_event = EventEnvelope.create(
        event_type="rule.proposed",
        event_id=f"mxev_fl_{result_id}_rule",
        occurred_at=data["observed_at"],
        producer=producer,
        subject={
            "kind": "failure_loop_rule_proposal",
            "rule_id": recommendation["rule_id"],
        },
        severity=data.get("severity", "warning"),
        correlation_id=data.get("correlation_id") or result_id,
        run_id=data.get("run_id"),
        references=references,
        payload={
            "external_result_id": result_id,
            "external_schema_version": data["schema_version"],
            "failure_signature": failure["signature"],
            "proposal": dict(recommendation),
            "enforced": False,
            "policy_action": "none",
            **({"metadata": data["metadata"]} if data.get("metadata") is not None else {}),
        },
    )
    return [failure_event, rule_event]


def convert_failure_loop_jsonl(input_path: str | Path, output_path: str | Path) -> int:
    """Convert failure-loop result JSONL into Matrix OS JSONL."""

    translated: list[EventEnvelope] = []
    try:
        with Path(input_path).open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                    events = translate_failure_loop_result(raw)
                    if isinstance(events, list):
                        translated.extend(events)
                    else:
                        translated.append(events)
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


def _validate_failure_loop_result(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValidationError("failure-loop result must be an object")
    for field in ("schema_version", "result_id", "observed_at", "source", "failure", "severity"):
        if field not in data:
            raise ValidationError(f"missing required field: {field}")
    if data["schema_version"] != FAILURE_LOOP_SCHEMA_VERSION:
        raise ValidationError(f"unsupported failure-loop schema_version: {data['schema_version']}")
    if not isinstance(data["result_id"], str) or not data["result_id"]:
        raise ValidationError("result_id must be a non-empty string")
    if not isinstance(data["observed_at"], str) or not data["observed_at"].endswith("Z"):
        raise ValidationError("observed_at must be UTC RFC3339 with Z suffix")
    if not isinstance(data["source"], dict) or not data["source"].get("name"):
        raise ValidationError("missing required field: source.name")
    if not isinstance(data["failure"], dict):
        raise ValidationError("failure must be an object")
    failure = data["failure"]
    for field in ("kind", "signature", "summary"):
        if not isinstance(failure.get(field), str) or not failure.get(field):
            raise ValidationError(f"missing required field: failure.{field}")
    if failure["kind"] not in SUPPORTED_FAILURE_KINDS:
        raise ValidationError(f"unsupported failure kind: {failure['kind']}")
    severity = data["severity"]
    if severity not in {"info", "warning", "error", "critical"}:
        raise ValidationError(f"unsupported severity: {severity}")
    recommendation = data.get("recommendation")
    if recommendation is not None:
        if not isinstance(recommendation, dict):
            raise ValidationError("recommendation must be an object or null")
        if recommendation.get("type") not in SUPPORTED_RECOMMENDATION_TYPES:
            raise ValidationError(f"unsupported recommendation type: {recommendation.get('type')}")
        for field in ("rule_id", "title"):
            if not isinstance(recommendation.get(field), str) or not recommendation.get(field):
                raise ValidationError(f"missing required field: recommendation.{field}")
    metadata = data.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValidationError("metadata must be an object")


def _extract_references(data: dict[str, Any]) -> list[dict[str, Any]] | None:
    failure = data.get("failure")
    if not isinstance(failure, dict):
        return None
    artifact_path = failure.get("artifact_path")
    if not isinstance(artifact_path, str) or not artifact_path:
        return None
    return [
        {
            "kind": "failure-loop.artifact",
            "path": artifact_path,
            "external_result_id": data["result_id"],
        }
    ]
