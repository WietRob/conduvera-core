"""Operator-readable evidence report tests for Matrix OS product coherence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conduvera.cli.main import app
from conduvera.evidence import EventEnvelope, EvidenceStore, ValidationError
from conduvera.evidence.adapters.agent_evidence_plane import convert_agent_evidence_plane_jsonl
from conduvera.evidence.adapters.failure_loop import convert_failure_loop_jsonl
from conduvera.evidence.adapters.safety_guard import convert_safety_guard_jsonl
from conduvera.evidence.reporting import build_operator_report, render_operator_report

runner = CliRunner()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _append_core_event(
    store: EvidenceStore,
    event_type: str,
    subject: dict,
    payload: dict,
    *,
    occurred_at: str,
    correlation_id: str = "CR-MXOS-001",
    references: list[dict] | None = None,
) -> None:
    store.append(
        EventEnvelope.create(
            event_type=event_type,
            producer={"name": "matrix-os", "version": "0.1.0", "adapter": "native"},
            subject=subject,
            payload=payload,
            severity="info",
            correlation_id=correlation_id,
            references=references,
            occurred_at=occurred_at,
        )
    )


def _agent_run_fixture() -> dict:
    return {
        "schema_version": "0.1.0",
        "event_id": "evt_agent_run_completed_coherence",
        "event_type": "agent.run.completed",
        "occurred_at": "2026-05-14T09:00:00Z",
        "producer": {"name": "agent-evidence-plane", "version": "0.1.0"},
        "subject": {"kind": "agent_run", "run_id": "run-900", "repo_path": "/repo/matrix-os"},
        "severity": "info",
        "correlation_id": "CR-MXOS-001",
        "run_id": "run-900",
        "payload": {"exit_code": 0, "changed_files": ["conduvera/auth.py"]},
        "evidence": {"artifact_path": "artifacts/run-900/stdout.txt", "sha256": "abc123"},
        "links": [{"rel": "implements", "event_id": "evt_cr_mxos_001"}],
    }


def _safety_block_fixture() -> dict:
    return {
        "schema_version": "safety-guard.result.v1",
        "result_id": "sg_blocked_coherence",
        "checked_at": "2026-05-14T09:05:00Z",
        "tool": {"name": "curaops-safety-guard", "version": "0.1.0"},
        "action": {"kind": "delete", "command": "rm production.db", "path": "production.db", "recursive": False},
        "verdict": "blocked",
        "reason": "Path matches protected pattern",
        "matched_pattern": ".*production.*",
        "exit_code": 1,
        "forced": False,
        "metadata": {"repo": "matrix-os"},
        "correlation_id": "CR-MXOS-001",
    }


def _failure_loop_fixture() -> dict:
    return {
        "schema_version": "failure-loop.result.v1",
        "result_id": "fl_coherence_001",
        "observed_at": "2026-05-14T09:10:00Z",
        "source": {"name": "failure-driven-loop", "version": "1.0.0"},
        "failure": {
            "kind": "test_failure",
            "signature": "pytest::test_product_coherence::AssertionError",
            "summary": "Scenario regression failed before rule proposal",
            "artifact_path": "reports/product-coherence.txt",
        },
        "recommendation": {
            "type": "rule_proposal",
            "rule_id": "rule_product_coherence_regression",
            "title": "Require product coherence scenario gate before merge",
        },
        "severity": "warning",
        "metadata": {"repo": "matrix-os"},
        "correlation_id": "CR-MXOS-001",
    }


def _combined_stream(tmp_path: Path) -> Path:
    store = EvidenceStore(tmp_path / "combined-events.jsonl")
    _append_core_event(
        store,
        "change_request.evidence.generated",
        {"kind": "change_request", "id": "CR-MXOS-001"},
        {
            "status": "approved",
            "change_type": "bugfix",
            "requirement_refs": ["SW-REQ-AUTH-007"],
            "operator_answer": "Agent run run-900 changed auth policy under approved CR-MXOS-001.",
        },
        occurred_at="2026-05-14T08:55:00Z",
        references=[{"kind": "requirement", "id": "SW-REQ-AUTH-007"}],
    )
    _append_core_event(
        store,
        "accountable_change.evidence.generated",
        {"kind": "accountable_change", "id": "AC-MXOS-001"},
        {
            "agent_id": "hermes-agent",
            "run_id": "run-900",
            "change_request_id": "CR-MXOS-001",
            "changed_files": ["conduvera/auth.py"],
            "requirement_refs": ["SW-REQ-AUTH-007"],
            "linkage_valid": True,
        },
        occurred_at="2026-05-14T08:58:00Z",
        references=[{"kind": "requirement", "id": "SW-REQ-AUTH-007"}],
    )
    _append_core_event(
        store,
        "aspice.check.completed",
        {"kind": "traceability_gap", "id": "SW-REQ-AUTH-007"},
        {
            "requirement_id": "SW-REQ-AUTH-007",
            "missing_link": "verification_case",
            "source_file": "docs/requirements/auth.md",
        },
        occurred_at="2026-05-14T09:02:00Z",
        references=[{"kind": "requirement", "id": "SW-REQ-AUTH-007"}],
    )

    agent_in = tmp_path / "agent-plane.jsonl"
    agent_out = tmp_path / "agent-events.jsonl"
    _write_jsonl(agent_in, [_agent_run_fixture()])
    convert_agent_evidence_plane_jsonl(agent_in, agent_out)

    safety_in = tmp_path / "safety-guard.jsonl"
    safety_out = tmp_path / "safety-events.jsonl"
    _write_jsonl(safety_in, [_safety_block_fixture()])
    convert_safety_guard_jsonl(safety_in, safety_out)

    failure_in = tmp_path / "failure-loop.jsonl"
    failure_out = tmp_path / "failure-events.jsonl"
    _write_jsonl(failure_in, [_failure_loop_fixture()])
    convert_failure_loop_jsonl(failure_in, failure_out)

    for path in (agent_out, safety_out, failure_out):
        for event in EvidenceStore(path).read_all():
            store.append(event)
    return store.path


def test_report_summarizes_counts_by_event_type_producer_subject_and_adapter(tmp_path: Path) -> None:
    report = build_operator_report(_combined_stream(tmp_path))

    assert report.total_events == 7
    assert report.event_types["agent.run.completed"] == 1
    assert report.event_types["safety_guard.action.blocked"] == 1
    assert report.producers["matrix-os"] == 3
    assert report.subjects["traceability_gap"] == 1
    assert report.adapters["native"] == 3
    assert report.adapters["matrix-os.agent-evidence-plane"] == 1
    assert report.adapters["matrix-os.safety-guard"] == 1
    assert report.adapters["matrix-os.failure-loop"] == 2


def test_report_answers_which_agent_changed_what_under_which_cr(tmp_path: Path) -> None:
    report = build_operator_report(_combined_stream(tmp_path))

    assert report.agent_actions == [
        {
            "agent_id": "hermes-agent",
            "run_id": "run-900",
            "change_request_id": "CR-MXOS-001",
            "changed_files": ["conduvera/auth.py"],
            "requirements": ["SW-REQ-AUTH-007"],
            "adapter": "native",
        }
    ]


def test_report_answers_what_risky_action_was_blocked_and_why(tmp_path: Path) -> None:
    report = build_operator_report(_combined_stream(tmp_path))

    assert report.blocked_actions == [
        {
            "action": "rm production.db",
            "action_kind": "delete",
            "path": "production.db",
            "reason": "Path matches protected pattern",
            "adapter": "matrix-os.safety-guard",
        }
    ]


def test_report_answers_what_failure_was_observed_and_what_rule_was_proposed(tmp_path: Path) -> None:
    report = build_operator_report(_combined_stream(tmp_path))

    assert report.failures == [
        {
            "kind": "test_failure",
            "signature": "pytest::test_product_coherence::AssertionError",
            "summary": "Scenario regression failed before rule proposal",
            "adapter": "matrix-os.failure-loop",
        }
    ]
    assert report.rule_proposals[0]["rule_id"] == "rule_product_coherence_regression"
    assert report.rule_proposals[0]["title"] == "Require product coherence scenario gate before merge"


def test_report_states_proposed_rules_are_not_enforced(tmp_path: Path) -> None:
    report = build_operator_report(_combined_stream(tmp_path))

    assert report.rule_proposals == [
        {
            "rule_id": "rule_product_coherence_regression",
            "title": "Require product coherence scenario gate before merge",
            "enforced": False,
            "policy_action": "none",
            "adapter": "matrix-os.failure-loop",
        }
    ]
    assert "not enforced" in render_operator_report(report, format="text")


def test_report_includes_requirements_and_traceability_gaps_when_present(tmp_path: Path) -> None:
    report = build_operator_report(_combined_stream(tmp_path))

    assert report.requirements == ["SW-REQ-AUTH-007"]
    assert report.traceability_gaps == [
        {
            "requirement_id": "SW-REQ-AUTH-007",
            "missing_link": "verification_case",
            "source_file": "docs/requirements/auth.md",
        }
    ]


def test_report_can_output_text_markdown_and_json(tmp_path: Path) -> None:
    report = build_operator_report(_combined_stream(tmp_path))

    text = render_operator_report(report, format="text")
    markdown = render_operator_report(report, format="markdown")
    json_report = json.loads(render_operator_report(report, format="json"))

    assert "Matrix OS Evidence Operator Report" in text
    assert "Agent actions" in text
    assert markdown.startswith("# Matrix OS Evidence Operator Report")
    assert "| Question | Answer |" in markdown
    assert json_report["total_events"] == 7
    assert json_report["rule_proposals"][0]["enforced"] is False


def test_cli_evidence_report_works_against_product_coherence_fixture_stream(tmp_path: Path) -> None:
    stream = _combined_stream(tmp_path)

    result = runner.invoke(app, ["evidence", "report", str(stream), "--format", "text"])

    assert result.exit_code == 0
    assert "Matrix OS Evidence Operator Report" in result.output
    assert "hermes-agent" in result.output
    assert "rm production.db" in result.output
    assert "rule_product_coherence_regression" in result.output


def test_malformed_missing_or_invalid_event_stream_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jsonl"
    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text('{"event_type":"agent.run.completed"}\n', encoding="utf-8")

    with pytest.raises(ValidationError):
        build_operator_report(missing)
    with pytest.raises(ValidationError):
        build_operator_report(invalid)

    missing_result = runner.invoke(app, ["evidence", "report", str(missing)])
    assert missing_result.exit_code == 1
    assert "Evidence report failed" in missing_result.output

    result = runner.invoke(app, ["evidence", "report", str(invalid)])
    assert result.exit_code == 1
    assert "Evidence report failed" in result.output


def test_report_does_not_require_external_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("operator report must not spawn external runtimes")

    monkeypatch.setattr("subprocess.run", _forbidden)

    report = build_operator_report(_combined_stream(tmp_path))

    assert report.total_events == 7
    assert report.boundaries["external_runtime_required"] is False
    assert report.boundaries["automatic_rule_enforcement"] is False
