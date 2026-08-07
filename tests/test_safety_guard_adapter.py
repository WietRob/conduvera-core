"""Tests for the Matrix OS Safety Guard adapter contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conduvera.cli.main import app
from conduvera.evidence import EventEnvelope, EvidenceStore, ValidationError, validate_event_stream
from conduvera.evidence.adapters.safety_guard import (
    SAFETY_GUARD_EVENT_TYPES,
    convert_safety_guard_jsonl,
    translate_safety_guard_result,
)

runner = CliRunner()


def safety_result(**overrides):
    data = {
        "schema_version": "safety-guard.result.v1",
        "result_id": "sg_001",
        "checked_at": "2026-05-13T18:45:00Z",
        "tool": {"name": "curaops-safety-guard", "version": "0.1.0", "repo": "curaops-safety-guard"},
        "action": {"kind": "delete", "command": "rm production.db", "path": "production.db", "recursive": False},
        "verdict": "blocked",
        "reason": "Path matches protected pattern",
        "matched_pattern": ".*production.*",
        "exit_code": 1,
        "forced": False,
        "metadata": {"cwd": "/repo", "user": "rob"},
    }
    data.update(overrides)
    return data


def test_safety_guard_adapter_converts_blocked_result_to_matrix_event() -> None:
    envelope = translate_safety_guard_result(safety_result())

    assert isinstance(envelope, EventEnvelope)
    assert envelope.event_type == "safety_guard.action.blocked"
    assert envelope.event_id.startswith("mxev_sg_sg_001")
    assert envelope.occurred_at == "2026-05-13T18:45:00Z"
    assert envelope.producer["name"] == "curaops-safety-guard"
    assert envelope.producer["adapter"] == "matrix-os.safety-guard"
    assert envelope.subject == {"kind": "safety_guard_action", "action_kind": "delete", "path": "production.db"}
    assert envelope.severity == "error"
    assert envelope.payload["external_result_id"] == "sg_001"
    assert envelope.payload["verdict"] == "blocked"
    assert envelope.payload["action"]["command"] == "rm production.db"
    assert envelope.payload["matched_pattern"] == ".*production.*"
    assert envelope.event_hash
    EventEnvelope.from_dict(envelope.to_dict())


def test_safety_guard_adapter_converts_allowed_result() -> None:
    envelope = translate_safety_guard_result(
        safety_result(
            result_id="sg_allowed",
            action={"kind": "delete", "command": "rm test.txt", "path": "test.txt", "recursive": False},
            verdict="allowed",
            reason="Path does not match any protected patterns",
            matched_pattern=None,
            exit_code=0,
        )
    )

    assert envelope.event_type == "safety_guard.action.allowed"
    assert envelope.severity == "info"
    assert envelope.subject["path"] == "test.txt"


def test_safety_guard_adapter_converts_approval_required_result() -> None:
    envelope = translate_safety_guard_result(
        safety_result(
            result_id="sg_confirm",
            verdict="approval_required",
            reason="Path matches confirmation pattern",
            matched_pattern="*.db",
            exit_code=2,
        )
    )

    assert envelope.event_type == "safety_guard.approval.required"
    assert envelope.severity == "warning"
    assert envelope.payload["verdict"] == "approval_required"


def test_safety_guard_adapter_converts_check_completed_result() -> None:
    envelope = translate_safety_guard_result(
        safety_result(
            result_id="sg_check",
            verdict="check_completed",
            reason="Safety check completed without action decision",
            exit_code=0,
        )
    )

    assert envelope.event_type == "safety_guard.check.completed"
    assert envelope.severity == "info"


def test_safety_guard_adapter_marks_forced_blocked_result_critical() -> None:
    envelope = translate_safety_guard_result(safety_result(forced=True))

    assert envelope.event_type == "safety_guard.action.blocked"
    assert envelope.severity == "critical"
    assert envelope.payload["forced"] is True


def test_safety_guard_adapter_rejects_malformed_result_missing_required_field() -> None:
    data = safety_result()
    del data["action"]

    with pytest.raises(ValidationError, match="missing required field: action"):
        translate_safety_guard_result(data)


def test_safety_guard_adapter_rejects_unsupported_verdict_fail_closed() -> None:
    with pytest.raises(ValidationError, match="unsupported Safety Guard verdict"):
        translate_safety_guard_result(safety_result(verdict="maybe"))


def test_safety_guard_adapter_rejects_action_without_path_or_command() -> None:
    with pytest.raises(ValidationError, match="action must include path or command"):
        translate_safety_guard_result(safety_result(action={"kind": "delete"}))


def test_safety_guard_event_type_policy_is_explicit() -> None:
    assert SAFETY_GUARD_EVENT_TYPES == {
        "safety_guard.check.completed",
        "safety_guard.action.allowed",
        "safety_guard.action.blocked",
        "safety_guard.approval.required",
    }


def test_safety_guard_output_roundtrips_through_evidence_store(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "events.jsonl")
    envelope = translate_safety_guard_result(safety_result())

    store.append(envelope)

    assert store.read_all() == [envelope]
    assert validate_event_stream(store.path)["valid"] is True


def test_convert_safety_guard_jsonl_writes_matrix_events(tmp_path: Path) -> None:
    source = tmp_path / "safety-guard.jsonl"
    target = tmp_path / "matrix-os.jsonl"
    source.write_text(json.dumps(safety_result()) + "\n", encoding="utf-8")

    converted = convert_safety_guard_jsonl(source, target)

    assert converted == 1
    output_events = EvidenceStore(target).read_all()
    assert len(output_events) == 1
    assert output_events[0].event_type == "safety_guard.action.blocked"


def test_convert_safety_guard_jsonl_fails_closed_on_invalid_line(tmp_path: Path) -> None:
    source = tmp_path / "safety-guard.jsonl"
    target = tmp_path / "matrix-os.jsonl"
    source.write_text(json.dumps(safety_result(verdict="unknown")) + "\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="line 1"):
        convert_safety_guard_jsonl(source, target)

    assert not target.exists()


def test_cli_convert_safety_guard_converts_then_validate_and_summarize_work(tmp_path: Path) -> None:
    source = tmp_path / "safety-guard.jsonl"
    target = tmp_path / "matrix-os.jsonl"
    source.write_text(json.dumps(safety_result()) + "\n", encoding="utf-8")

    result = runner.invoke(app, ["evidence", "convert-safety-guard", str(source), str(target)])

    assert result.exit_code == 0
    assert "Converted 1 Safety Guard results" in result.stdout
    assert runner.invoke(app, ["evidence", "validate", str(target)]).exit_code == 0
    summary = runner.invoke(app, ["evidence", "summarize", str(target)])
    assert summary.exit_code == 0
    assert "safety_guard.action.blocked" in summary.stdout


def test_cli_convert_safety_guard_rejects_invalid_input(tmp_path: Path) -> None:
    source = tmp_path / "safety-guard.jsonl"
    target = tmp_path / "matrix-os.jsonl"
    source.write_text(json.dumps(safety_result(verdict="unknown")) + "\n", encoding="utf-8")

    result = runner.invoke(app, ["evidence", "convert-safety-guard", str(source), str(target)])

    assert result.exit_code == 1
    assert "unsupported Safety Guard verdict" in result.stdout
    assert not target.exists()
