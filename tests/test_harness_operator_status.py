"""Product-value tests for the read-only Matrix OS harness operator status."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from curaops.cli.main import app
from curaops.evidence import EventEnvelope, EvidenceStore
from curaops.harness.operator_status import build_harness_operator_status, render_harness_operator_status

runner = CliRunner()


def _append_event(
    store: EvidenceStore,
    event_type: str,
    subject: dict,
    payload: dict,
    *,
    occurred_at: str,
    producer: dict | None = None,
    correlation_id: str = "CR-MXOS-R-001",
    references: list[dict] | None = None,
) -> None:
    store.append(
        EventEnvelope.create(
            event_type=event_type,
            producer=producer or {"name": "matrix-os", "version": "0.1.0", "adapter": "native"},
            subject=subject,
            payload=payload,
            severity="info",
            correlation_id=correlation_id,
            references=references,
            occurred_at=occurred_at,
        )
    )


def _operator_stream(tmp_path: Path) -> Path:
    store = EvidenceStore(tmp_path / "operator-status.events.jsonl")
    _append_event(
        store,
        "change_request.evidence.generated",
        {"kind": "change_request", "id": "CR-MXOS-R-001"},
        {"status": "approved", "change_type": "feature", "requirement_refs": ["MXOS-OP-001"]},
        occurred_at="2026-05-18T07:00:00Z",
        references=[{"kind": "requirement", "id": "MXOS-OP-001"}],
    )
    _append_event(
        store,
        "accountable_change.evidence.generated",
        {"kind": "accountable_change", "id": "AC-MXOS-R-001"},
        {
            "agent_id": "hermes-agent",
            "run_id": "run-r-001",
            "change_request_id": "CR-MXOS-R-001",
            "changed_files": ["curaops/harness/operator_status.py"],
            "requirement_refs": ["MXOS-OP-001"],
        },
        occurred_at="2026-05-18T07:01:00Z",
        references=[{"kind": "requirement", "id": "MXOS-OP-001"}],
    )
    _append_event(
        store,
        "safety_guard.action.blocked",
        {"kind": "safety_action", "action_kind": "shell"},
        {"action": {"kind": "shell", "command": "rm -rf ."}, "reason": "destructive action"},
        producer={"name": "curaops-safety-guard", "version": "0.1.0", "adapter": "matrix-os.safety-guard"},
        occurred_at="2026-05-18T07:02:00Z",
    )
    _append_event(
        store,
        "failure.observed",
        {"kind": "failure", "failure_kind": "test_failure", "signature": "pytest::operator"},
        {"failure": {"kind": "test_failure", "signature": "pytest::operator", "summary": "operator fixture failed"}},
        producer={"name": "failure-driven-loop", "version": "0.1.0", "adapter": "matrix-os.failure-loop"},
        occurred_at="2026-05-18T07:03:00Z",
    )
    _append_event(
        store,
        "rule.proposed",
        {"kind": "rule_proposal", "rule_id": "rule_operator_fixture"},
        {
            "proposal": {"rule_id": "rule_operator_fixture", "title": "Keep operator status fixture green"},
            "enforced": False,
            "policy_action": "none",
        },
        producer={"name": "failure-driven-loop", "version": "0.1.0", "adapter": "matrix-os.failure-loop"},
        occurred_at="2026-05-18T07:04:00Z",
    )
    _append_event(
        store,
        "aspice.check.completed",
        {"kind": "traceability_gap", "id": "MXOS-OP-001"},
        {
            "requirement_id": "MXOS-OP-001",
            "missing_link": "verification_case",
            "source_file": "docs/operator-workflow.md",
        },
        occurred_at="2026-05-18T07:05:00Z",
        references=[{"kind": "requirement", "id": "MXOS-OP-001"}],
    )
    return store.path


def test_harness_operator_status_connects_evidence_adapters_gateway_and_ui(tmp_path: Path) -> None:
    status = build_harness_operator_status(_operator_stream(tmp_path))

    assert status.evidence.total_events == 6
    assert status.signals.approved_cr_present is True
    assert status.signals.agent_action_present is True
    assert status.signals.safety_block_present is True
    assert status.signals.failure_or_rule_proposal_present is True
    assert status.signals.traceability_gap_present is True
    assert {adapter.adapter_id for adapter in status.adapters} == {
        "agent-evidence-plane",
        "safety-guard",
        "failure-loop",
    }
    assert {runner.runner_id for runner in status.runners} == {"hermes", "opencode", "local-shell", "pi-agent-harness"}
    assert status.ui_attach_point.surface_id == "matrix-ui-code-editor"
    assert status.boundaries["read_only"] is True
    assert status.boundaries["runtime_execution"] is False


def test_harness_operator_status_produces_actionable_next_step_hints(tmp_path: Path) -> None:
    status = build_harness_operator_status(_operator_stream(tmp_path))

    assert status.next_step_hints == [
        "Approved CR CR-MXOS-R-001 is present; inspect linked agent action before execution.",
        "Agent action run-r-001 by hermes-agent is present; verify changed files and requirements.",
        "Safety block present for rm -rf .; keep action blocked until explicit human review.",
        "Failure/rule proposal present; treat proposed rule as evidence only, not enforcement.",
        "Traceability gap MXOS-OP-001 missing verification_case; create or link verification evidence.",
    ]


def test_harness_operator_status_renders_product_facing_read_only_summary(tmp_path: Path) -> None:
    status = build_harness_operator_status(_operator_stream(tmp_path))
    rendered = render_harness_operator_status(status)

    assert "Matrix OS Harness Operator Status" in rendered
    assert "Read-only: yes" in rendered
    assert "Runners/tools/surfaces described, not executed" in rendered
    assert "Evidence events: 6" in rendered
    assert "Adapters: agent-evidence-plane, safety-guard, failure-loop" in rendered
    assert "UI attach point: matrix-ui-code-editor" in rendered
    assert "Approved CR CR-MXOS-R-001" in rendered


def test_cli_harness_status_uses_event_stream_and_default_read_only_boundaries(tmp_path: Path) -> None:
    result = runner.invoke(app, ["harness", "status", "--events", str(_operator_stream(tmp_path))])

    assert result.exit_code == 0
    assert "Matrix OS Harness Operator Status" in result.output
    assert "Evidence events: 6" in result.output
    assert "Hermes Agent Runner" in result.output
    assert "CuraOps Safety Guard" in result.output
    assert "No runtime execution" in result.output


def test_cli_harness_status_works_with_committed_product_coherence_fixture() -> None:
    fixture = Path("tests/fixtures/evidence/operator_report/product_coherence.events.jsonl")

    result = runner.invoke(app, ["harness", "status", "--events", str(fixture)])

    assert result.exit_code == 0
    assert "Approved CR CR-MXOS-001" in result.output
    assert "UI attach point: matrix-ui-code-editor" in result.output
    assert "failure-loop" in result.output


def test_harness_operator_status_does_not_spawn_or_execute_runtimes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("harness status must be read-only")

    monkeypatch.setattr("subprocess.run", _forbidden)

    status = build_harness_operator_status(_operator_stream(tmp_path))

    assert status.boundaries["runtime_execution"] is False
    assert all(not runner.runtime_enabled for runner in status.runners)
