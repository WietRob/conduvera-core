"""Tests for Matrix OS evidence backbone adapter contract."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner
import pytest

from curaops.cli.main import app

from curaops.evidence import (
    CORE_EVENT_TYPES,
    EventEnvelope,
    EvidenceStore,
    ValidationError,
    default_event_store_path,
    summarize_event_stream,
    validate_event_stream,
)


def minimal_event(**overrides) -> EventEnvelope:
    data = {
        "event_type": "gate.run.completed",
        "producer": {"name": "matrix-os.tests", "version": "0.1"},
        "subject": {"kind": "gate", "id": "unit-gate"},
        "payload": {"status": "passed", "tests": 1},
        "severity": "info",
        "correlation_id": "CR-TEST-001",
    }
    data.update(overrides)
    return EventEnvelope.create(**data)


def test_core_registry_contains_matrix_os_evidence_events() -> None:
    assert CORE_EVENT_TYPES == {
        "change_request.evidence.generated",
        "accountable_change.evidence.generated",
        "aspice.check.completed",
        "gate.run.completed",
    }


def test_event_envelope_create_adds_id_timestamp_and_hash_reference() -> None:
    event = minimal_event(references=[{"kind": "file", "path": "changes/evidence/CR-1.json"}])
    data = event.to_dict()

    assert data["schema_version"] == "MXOS-EVIDENCE-1.0.0"
    assert data["event_id"].startswith("mxev_")
    assert data["occurred_at"].endswith("Z")
    assert data["event_hash"].startswith("sha256:")
    assert data["integrity"]["hash"] == data["event_hash"]
    assert data["references"] == [{"kind": "file", "path": "changes/evidence/CR-1.json"}]


def test_event_validation_rejects_unknown_event_type() -> None:
    with pytest.raises(ValidationError, match="unsupported event_type"):
        minimal_event(event_type="safety_guard.verdict.generated")


def test_event_validation_rejects_hash_tampering() -> None:
    event = minimal_event().to_dict()
    event["payload"]["status"] = "failed"

    with pytest.raises(ValidationError, match="event_hash mismatch"):
        EventEnvelope.from_dict(event)


def test_event_validation_rejects_missing_hash() -> None:
    event = minimal_event().to_dict()
    event.pop("event_hash")
    event["integrity"].pop("hash")

    with pytest.raises(ValidationError, match="missing required field: event_hash"):
        EventEnvelope.from_dict(event)


def test_jsonl_store_append_read_validate_and_summarize_roundtrip(tmp_path: Path) -> None:
    store_path = tmp_path / "matrix-os" / "events.jsonl"
    store = EvidenceStore(store_path)
    first = minimal_event(event_type="change_request.evidence.generated")
    second = minimal_event(event_type="accountable_change.evidence.generated", subject={"kind": "accountable_change", "id": "AC-1"})

    store.append(first)
    store.append(second)

    assert store_path.exists()
    assert [event.event_id for event in store.read_all()] == [first.event_id, second.event_id]
    assert validate_event_stream(store_path) == {"valid": True, "events": 2, "errors": []}
    assert summarize_event_stream(store_path) == {
        "events": 2,
        "event_types": {
            "accountable_change.evidence.generated": 1,
            "change_request.evidence.generated": 1,
        },
        "producers": {"matrix-os.tests": 2},
        "subjects": {"accountable_change": 1, "gate": 1},
    }


def test_validate_event_stream_reports_line_errors(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps(minimal_event().to_dict()) + "\n" + "{not-json}\n", encoding="utf-8")

    result = validate_event_stream(path)

    assert result["valid"] is False
    assert result["events"] == 1
    assert result["errors"][0].startswith("line 2: invalid JSON")


def test_default_event_store_path_uses_project_changes_evidence_events(tmp_path: Path) -> None:
    assert default_event_store_path(tmp_path) == tmp_path / "changes" / "evidence" / "events.jsonl"


def test_evidence_cli_validate_and_summarize(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "events.jsonl")
    store.append(minimal_event())
    runner = CliRunner()

    validate = runner.invoke(app, ["evidence", "validate", str(store.path)])
    summarize = runner.invoke(app, ["evidence", "summarize", str(store.path)])

    assert validate.exit_code == 0
    assert "Evidence stream valid" in validate.output
    assert summarize.exit_code == 0
    assert "Evidence events" in summarize.output
    assert "gate.run.completed" in summarize.output
