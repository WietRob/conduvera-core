"""Thin adapter from CuraOps Safety Guard result JSONL to Matrix OS events.

This module intentionally does not execute Safety Guard, shell commands, or
filesystem operations. It translates already-produced Safety Guard result
objects into the Matrix OS ``EventEnvelope`` contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from conduvera.evidence import EventEnvelope, EvidenceStore, ValidationError

SAFETY_GUARD_SCHEMA_VERSION = "safety-guard.result.v1"
SAFETY_GUARD_EVENT_TYPES = {
    "safety_guard.check.completed",
    "safety_guard.action.allowed",
    "safety_guard.action.blocked",
    "safety_guard.approval.required",
}
VERDICT_EVENT_TYPES = {
    "check_completed": "safety_guard.check.completed",
    "allowed": "safety_guard.action.allowed",
    "blocked": "safety_guard.action.blocked",
    "approval_required": "safety_guard.approval.required",
}
ADAPTER_NAME = "matrix-os.safety-guard"


def translate_safety_guard_result(data: dict[str, Any]) -> EventEnvelope:
    """Translate one Safety Guard result dictionary into Matrix OS evidence.

    Unsupported or malformed results fail closed with ``ValidationError``. The
    adapter is translation-only and never executes commands or invokes Safety
    Guard itself.
    """

    _validate_safety_guard_result(data)
    result_id = data["result_id"]
    verdict = data["verdict"]
    action = data["action"]
    event_type = VERDICT_EVENT_TYPES[verdict]
    path = action.get("path")
    command = action.get("command")
    producer = {
        **dict(data["tool"]),
        "adapter": ADAPTER_NAME,
        "external_schema_version": data["schema_version"],
    }
    subject = {
        "kind": "safety_guard_action",
        "action_kind": action.get("kind", "unknown"),
    }
    if path:
        subject["path"] = path
    elif command:
        subject["command"] = command

    payload = {
        "external_result_id": result_id,
        "external_schema_version": data["schema_version"],
        "verdict": verdict,
        "reason": data["reason"],
        "action": dict(action),
        "exit_code": data.get("exit_code"),
        "forced": bool(data.get("forced", False)),
    }
    if data.get("matched_pattern"):
        payload["matched_pattern"] = data["matched_pattern"]
    if data.get("metadata") is not None:
        payload["metadata"] = data["metadata"]

    return EventEnvelope.create(
        event_type=event_type,
        event_id=f"mxev_sg_{result_id}",
        occurred_at=data["checked_at"],
        producer=producer,
        subject=subject,
        severity=_severity_for_result(verdict, bool(data.get("forced", False))),
        correlation_id=data.get("correlation_id") or result_id,
        run_id=data.get("run_id"),
        references=_extract_references(data),
        payload=payload,
    )


def convert_safety_guard_jsonl(input_path: str | Path, output_path: str | Path) -> int:
    """Convert Safety Guard result JSONL into Matrix OS JSONL."""

    translated: list[EventEnvelope] = []
    try:
        with Path(input_path).open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                    translated.append(translate_safety_guard_result(raw))
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


def _validate_safety_guard_result(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValidationError("Safety Guard result must be an object")
    for field in ("schema_version", "result_id", "checked_at", "tool", "action", "verdict", "reason"):
        if field not in data:
            raise ValidationError(f"missing required field: {field}")
    if data["schema_version"] != SAFETY_GUARD_SCHEMA_VERSION:
        raise ValidationError(f"unsupported Safety Guard schema_version: {data['schema_version']}")
    if not isinstance(data["result_id"], str) or not data["result_id"]:
        raise ValidationError("result_id must be a non-empty string")
    if not isinstance(data["checked_at"], str) or not data["checked_at"].endswith("Z"):
        raise ValidationError("checked_at must be UTC RFC3339 with Z suffix")
    if not isinstance(data["tool"], dict) or not data["tool"].get("name"):
        raise ValidationError("missing required field: tool.name")
    if not isinstance(data["action"], dict):
        raise ValidationError("action must be an object")
    if not data["action"].get("path") and not data["action"].get("command"):
        raise ValidationError("action must include path or command")
    if data["verdict"] not in VERDICT_EVENT_TYPES:
        raise ValidationError(f"unsupported Safety Guard verdict: {data['verdict']}")
    if not isinstance(data["reason"], str) or not data["reason"]:
        raise ValidationError("reason must be a non-empty string")
    metadata = data.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValidationError("metadata must be an object")


def _severity_for_result(verdict: str, forced: bool) -> str:
    if forced and verdict == "blocked":
        return "critical"
    return {
        "check_completed": "info",
        "allowed": "info",
        "blocked": "error",
        "approval_required": "warning",
    }[verdict]


def _extract_references(data: dict[str, Any]) -> list[dict[str, Any]] | None:
    action = data.get("action")
    if not isinstance(action, dict):
        return None
    path = action.get("path")
    if not isinstance(path, str) or not path:
        return None
    return [
        {
            "kind": "safety-guard.action-path",
            "path": path,
            "external_result_id": data["result_id"],
        }
    ]
