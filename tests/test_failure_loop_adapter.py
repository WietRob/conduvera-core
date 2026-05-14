"""Tests for the Matrix OS failure-driven-loop thin adapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from curaops.cli.main import app
from curaops.evidence import EvidenceStore, ValidationError, validate_event_stream
from curaops.evidence.adapters.failure_loop import (
    FAILURE_LOOP_EVENT_TYPES,
    convert_failure_loop_jsonl,
    translate_failure_loop_result,
)
from curaops.evidence.adapters.registry import get_adapter_descriptor

runner = CliRunner()


def _base_result(**overrides):
    data = {
        "schema_version": "failure-loop.result.v1",
        "result_id": "fl_001",
        "observed_at": "2026-05-13T18:45:00Z",
        "source": {"name": "failure-driven-loop", "version": "1.0.0"},
        "failure": {
            "kind": "test_failure",
            "signature": "pytest::test_example::AssertionError",
            "summary": "Assertion failed in test_example",
            "artifact_path": "reports/pytest.txt",
        },
        "recommendation": {
            "type": "rule_proposal",
            "rule_id": "rule_pytest_assertion",
            "title": "Require regression test before merge",
        },
        "severity": "warning",
        "metadata": {"repo": "matrix-os"},
    }
    data.update(overrides)
    return data


def test_supported_failure_loop_event_types_are_explicit() -> None:
    assert FAILURE_LOOP_EVENT_TYPES == {"failure.observed", "rule.proposed"}


def test_translates_failure_observed_without_enforcing_rule() -> None:
    event = translate_failure_loop_result(_base_result(recommendation=None))

    assert event.event_type == "failure.observed"
    assert event.event_id == "mxev_fl_fl_001_failure"
    assert event.occurred_at == "2026-05-13T18:45:00Z"
    assert event.producer["adapter"] == "matrix-os.failure-loop"
    assert event.producer["name"] == "failure-driven-loop"
    assert event.subject == {
        "kind": "failure_loop_failure",
        "failure_kind": "test_failure",
        "signature": "pytest::test_example::AssertionError",
    }
    assert event.severity == "warning"
    assert event.payload["external_result_id"] == "fl_001"
    assert event.payload["failure"]["summary"] == "Assertion failed in test_example"
    assert event.payload["recommendation"] is None
    assert event.payload["enforced"] is False
    assert event.references == [
        {
            "kind": "failure-loop.artifact",
            "path": "reports/pytest.txt",
            "external_result_id": "fl_001",
        }
    ]


def test_translates_rule_proposed_as_evidence_not_enforcement() -> None:
    events = translate_failure_loop_result(_base_result())

    assert isinstance(events, list)
    assert [event.event_type for event in events] == ["failure.observed", "rule.proposed"]
    rule_event = events[1]
    assert rule_event.event_id == "mxev_fl_fl_001_rule"
    assert rule_event.subject == {
        "kind": "failure_loop_rule_proposal",
        "rule_id": "rule_pytest_assertion",
    }
    assert rule_event.payload["proposal"]["title"] == "Require regression test before merge"
    assert rule_event.payload["enforced"] is False
    assert rule_event.payload["policy_action"] == "none"
    assert rule_event.references == [
        {
            "kind": "failure-loop.artifact",
            "path": "reports/pytest.txt",
            "external_result_id": "fl_001",
        }
    ]


def test_rejects_unknown_schema_version() -> None:
    with pytest.raises(ValidationError, match="unsupported failure-loop schema_version"):
        translate_failure_loop_result(_base_result(schema_version="failure-loop.result.v2"))


def test_rejects_malformed_result() -> None:
    with pytest.raises(ValidationError, match="missing required field: failure.signature"):
        translate_failure_loop_result(_base_result(failure={"kind": "test_failure"}))


def test_rejects_unsupported_failure_kind() -> None:
    data = _base_result()
    data["failure"]["kind"] = "runtime_outage"

    with pytest.raises(ValidationError, match="unsupported failure kind"):
        translate_failure_loop_result(data)


def test_rejects_unsupported_recommendation_type() -> None:
    data = _base_result()
    data["recommendation"]["type"] = "enforce_rule"

    with pytest.raises(ValidationError, match="unsupported recommendation type"):
        translate_failure_loop_result(data)


def test_rejects_invalid_timestamp() -> None:
    with pytest.raises(ValidationError, match="observed_at must be UTC RFC3339"):
        translate_failure_loop_result(_base_result(observed_at="2026-05-13 18:45:00"))


def test_convert_jsonl_outputs_valid_event_stream(tmp_path: Path) -> None:
    input_path = tmp_path / "failure-loop.jsonl"
    output_path = tmp_path / "matrix-events.jsonl"
    input_path.write_text(json.dumps(_base_result()) + "\n", encoding="utf-8")

    count = convert_failure_loop_jsonl(input_path, output_path)

    assert count == 2
    validation = validate_event_stream(output_path)
    assert validation == {"valid": True, "events": 2, "errors": []}
    events = EvidenceStore(output_path).read_all()
    assert [event.event_type for event in events] == ["failure.observed", "rule.proposed"]


def test_convert_jsonl_rejects_malformed_json(tmp_path: Path) -> None:
    input_path = tmp_path / "failure-loop.jsonl"
    output_path = tmp_path / "matrix-events.jsonl"
    input_path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="line 1: invalid JSON"):
        convert_failure_loop_jsonl(input_path, output_path)


def test_cli_convert_failure_loop_works(tmp_path: Path) -> None:
    input_path = tmp_path / "failure-loop.jsonl"
    output_path = tmp_path / "matrix-events.jsonl"
    input_path.write_text(json.dumps(_base_result()) + "\n", encoding="utf-8")

    result = runner.invoke(app, ["evidence", "convert-failure-loop", str(input_path), str(output_path)])

    assert result.exit_code == 0
    assert "Converted 2 failure-loop events" in result.output
    validation = validate_event_stream(output_path)
    assert validation == {"valid": True, "events": 2, "errors": []}
    events = EvidenceStore(output_path).read_all()
    assert [event.event_type for event in events] == ["failure.observed", "rule.proposed"]


def test_registry_descriptor_for_failure_loop() -> None:
    descriptor = get_adapter_descriptor("failure-loop")

    assert descriptor.name == "failure-driven-loop Thin Adapter"
    assert descriptor.source_project == "failure-driven-loop"
    assert descriptor.module_path == "curaops.evidence.adapters.failure_loop"
    assert descriptor.docs_path == "docs/MATRIX_OS_FAILURE_LOOP_ADAPTER.md"
    assert descriptor.input_contract == "failure-loop result JSONL schema_version failure-loop.result.v1"
    assert descriptor.execution_mode == "translation-only"
    assert descriptor.production_status == "local-contract-only / not-production-runtime"
    assert descriptor.external_repo_policy == "standalone; not vendored; not executed by Matrix OS"
    assert descriptor.cli_commands == (
        "python3 -m curaops.cli.main evidence convert-failure-loop INPUT.jsonl OUTPUT.jsonl",
    )
    assert descriptor.supported_event_types == ("failure.observed", "rule.proposed")
