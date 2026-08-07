"""Tests for the Matrix OS agent-evidence-plane thin adapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conduvera.cli.main import app
from conduvera.evidence import EventEnvelope, EvidenceStore, ValidationError, validate_event_stream
from conduvera.evidence.adapters.agent_evidence_plane import (
    AGENT_EVIDENCE_PLANE_EVENT_TYPES,
    convert_agent_evidence_plane_jsonl,
    translate_agent_evidence_plane_event,
)

runner = CliRunner()


def external_event(**overrides):
    data = {
        "schema_version": "0.1.0",
        "event_id": "evt_agent_run_completed",
        "event_type": "agent.run.completed",
        "occurred_at": "2026-05-11T08:00:00Z",
        "producer": {"name": "agent-evidence-plane", "version": "0.1.0", "repo": "agent-evidence-plane"},
        "subject": {"kind": "agent_run", "run_id": "run-123", "repo_path": "/repo"},
        "severity": "info",
        "correlation_id": "run-123",
        "run_id": "run-123",
        "payload": {"exit_code": 0, "stdout_path": "artifacts/stdout.txt", "stderr_path": None},
        "evidence": {"artifact_path": "artifacts/stdout.txt", "sha256": "abc123"},
        "links": [{"rel": "caused_by", "event_id": "evt_agent_run_started"}],
    }
    data.update(overrides)
    return data


def test_adapter_translates_supported_external_event_to_matrix_os_envelope() -> None:
    envelope = translate_agent_evidence_plane_event(external_event())

    assert isinstance(envelope, EventEnvelope)
    assert envelope.event_type == "agent.run.completed"
    assert envelope.event_id.startswith("mxev_aep_evt_agent_run_completed")
    assert envelope.occurred_at == "2026-05-11T08:00:00Z"
    assert envelope.producer["name"] == "agent-evidence-plane"
    assert envelope.producer["adapter"] == "matrix-os.agent-evidence-plane"
    assert envelope.subject == {"kind": "agent_run", "run_id": "run-123", "repo_path": "/repo"}
    assert envelope.payload["external_event_id"] == "evt_agent_run_completed"
    assert envelope.payload["external_event_type"] == "agent.run.completed"
    assert envelope.payload["external_payload"]["exit_code"] == 0
    assert envelope.run_id == "run-123"
    assert envelope.correlation_id == "run-123"
    assert envelope.event_hash
    EventEnvelope.from_dict(envelope.to_dict())


def test_adapter_rejects_malformed_external_event_missing_required_field() -> None:
    data = external_event()
    del data["producer"]

    with pytest.raises(ValidationError, match="missing required field: producer"):
        translate_agent_evidence_plane_event(data)


def test_adapter_preserves_artifact_reference_when_present() -> None:
    envelope = translate_agent_evidence_plane_event(external_event())

    assert envelope.references == [
        {
            "kind": "agent-evidence-plane.evidence",
            "path": "artifacts/stdout.txt",
            "sha256": "abc123",
            "external_event_id": "evt_agent_run_completed",
        }
    ]
    assert envelope.links == [
        {
            "rel": "external:caused_by",
            "external_event_id": "evt_agent_run_started",
        }
    ]


def test_adapter_output_roundtrips_through_evidence_store(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "events.jsonl")
    envelope = translate_agent_evidence_plane_event(external_event())

    store.append(envelope)

    assert store.read_all() == [envelope]
    assert validate_event_stream(store.path)["valid"] is True


def test_adapter_rejects_unknown_external_event_type_fail_closed() -> None:
    with pytest.raises(ValidationError, match="unsupported agent-evidence-plane event_type"):
        translate_agent_evidence_plane_event(external_event(event_type="unknown.event"))


def test_adapter_rejects_external_event_without_object_payload() -> None:
    with pytest.raises(ValidationError, match="payload must be an object"):
        translate_agent_evidence_plane_event(external_event(payload="not-object"))


def test_adapter_event_type_policy_is_explicit_and_not_arbitrary() -> None:
    assert "agent.run.completed" in AGENT_EVIDENCE_PLANE_EVENT_TYPES
    assert "agent.run.started" in AGENT_EVIDENCE_PLANE_EVENT_TYPES
    assert "agent.run.failed" in AGENT_EVIDENCE_PLANE_EVENT_TYPES
    assert "failure.observed" in AGENT_EVIDENCE_PLANE_EVENT_TYPES
    assert "unknown.event" not in AGENT_EVIDENCE_PLANE_EVENT_TYPES


def test_convert_agent_evidence_plane_jsonl_writes_matrix_os_events(tmp_path: Path) -> None:
    source = tmp_path / "agent-plane.jsonl"
    target = tmp_path / "matrix-os.jsonl"
    source.write_text(json.dumps(external_event()) + "\n", encoding="utf-8")

    converted = convert_agent_evidence_plane_jsonl(source, target)

    assert converted == 1
    output_events = EvidenceStore(target).read_all()
    assert len(output_events) == 1
    assert output_events[0].event_type == "agent.run.completed"


def test_convert_agent_evidence_plane_jsonl_fails_closed_on_invalid_line(tmp_path: Path) -> None:
    source = tmp_path / "agent-plane.jsonl"
    target = tmp_path / "matrix-os.jsonl"
    source.write_text(json.dumps(external_event(event_type="unknown.event")) + "\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="line 1"):
        convert_agent_evidence_plane_jsonl(source, target)

    assert not target.exists()


def test_cli_convert_agent_plane_converts_then_validate_and_summarize_work(tmp_path: Path) -> None:
    source = tmp_path / "agent-plane.jsonl"
    target = tmp_path / "matrix-os.jsonl"
    source.write_text(json.dumps(external_event()) + "\n", encoding="utf-8")

    result = runner.invoke(app, ["evidence", "convert-agent-plane", str(source), str(target)])

    assert result.exit_code == 0
    assert "Converted 1 agent-evidence-plane events" in result.stdout
    assert runner.invoke(app, ["evidence", "validate", str(target)]).exit_code == 0
    assert runner.invoke(app, ["evidence", "summarize", str(target)]).exit_code == 0


def test_cli_convert_agent_plane_rejects_invalid_input(tmp_path: Path) -> None:
    source = tmp_path / "agent-plane.jsonl"
    target = tmp_path / "matrix-os.jsonl"
    source.write_text(json.dumps(external_event(event_type="unknown.event")) + "\n", encoding="utf-8")

    result = runner.invoke(app, ["evidence", "convert-agent-plane", str(source), str(target)])

    assert result.exit_code == 1
    assert "unsupported agent-evidence-plane event_type" in result.stdout
    assert not target.exists()
