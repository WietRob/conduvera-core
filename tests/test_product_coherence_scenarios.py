"""Product-coherence scenario tests for Matrix OS as an accountability/compliance harness."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from curaops.cli.main import app
from curaops.evidence import EventEnvelope, EvidenceStore, summarize_event_stream, validate_event_stream
from curaops.evidence.adapters.agent_evidence_plane import convert_agent_evidence_plane_jsonl
from curaops.evidence.adapters.failure_loop import convert_failure_loop_jsonl
from curaops.evidence.adapters.registry import get_adapter_descriptor, list_adapter_descriptors
from curaops.evidence.adapters.safety_guard import convert_safety_guard_jsonl
from curaops.harness.scaffolding import get_scaffolding_slice

runner = CliRunner()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _store_core_event(store: EvidenceStore, event_type: str, subject: dict, payload: dict, *, correlation_id: str = "CR-MXOS-001") -> None:
    store.append(
        EventEnvelope.create(
            event_type=event_type,
            producer={"name": "matrix-os", "version": "0.1.0"},
            subject=subject,
            payload=payload,
            severity="info",
            correlation_id=correlation_id,
        )
    )


def _approved_change_scenario(store: EvidenceStore) -> None:
    _store_core_event(
        store,
        "change_request.evidence.generated",
        {"kind": "change_request", "id": "CR-MXOS-001"},
        {
            "status": "approved",
            "change_type": "bugfix",
            "requirement_refs": ["SW-REQ-AUTH-007"],
            "operator_answer": "Agent run run-900 changed auth policy under approved CR-MXOS-001 with linked evidence.",
        },
    )
    _store_core_event(
        store,
        "accountable_change.evidence.generated",
        {"kind": "accountable_change", "id": "AC-MXOS-001"},
        {
            "agent_id": "hermes-agent",
            "run_id": "run-900",
            "change_request_id": "CR-MXOS-001",
            "requirement_refs": ["SW-REQ-AUTH-007"],
            "linkage_valid": True,
        },
    )


def _aspice_traceability_gap(store: EvidenceStore) -> None:
    _store_core_event(
        store,
        "aspice.check.completed",
        {"kind": "traceability_gap", "id": "SW-REQ-AUTH-007"},
        {
            "requirement_id": "SW-REQ-AUTH-007",
            "missing_link": "verification_case",
            "source_file": "docs/requirements/auth.md",
            "operator_answer": "SW-REQ-AUTH-007 lacks a verification-case link.",
        },
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
        "payload": {"exit_code": 0, "changed_files": ["curaops/auth.py"]},
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
    }


def _combined_stream(tmp_path: Path) -> Path:
    store = EvidenceStore(tmp_path / "combined-events.jsonl")
    _approved_change_scenario(store)
    _aspice_traceability_gap(store)

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


def test_scenario_a_answers_which_agent_changed_what_under_which_cr(tmp_path: Path) -> None:
    stream = _combined_stream(tmp_path)
    events = EvidenceStore(stream).read_all()

    cr_event = next(event for event in events if event.event_type == "change_request.evidence.generated")
    aal_event = next(event for event in events if event.event_type == "accountable_change.evidence.generated")
    run_event = next(event for event in events if event.event_type == "agent.run.completed")
    descriptor = get_adapter_descriptor("agent-evidence-plane")

    assert cr_event.payload["status"] == "approved"
    assert aal_event.payload["agent_id"] == "hermes-agent"
    assert aal_event.payload["change_request_id"] == "CR-MXOS-001"
    assert aal_event.payload["requirement_refs"] == ["SW-REQ-AUTH-007"]
    assert run_event.run_id == "run-900"
    assert descriptor.execution_mode == "translation-only"


def test_scenario_b_answers_what_risky_action_was_blocked(tmp_path: Path) -> None:
    stream = _combined_stream(tmp_path)
    events = EvidenceStore(stream).read_all()
    blocked = next(event for event in events if event.event_type == "safety_guard.action.blocked")

    assert blocked.producer["name"] == "curaops-safety-guard"
    assert blocked.payload["action"]["command"] == "rm production.db"
    assert blocked.payload["reason"] == "Path matches protected pattern"
    assert summarize_event_stream(stream)["event_types"]["safety_guard.action.blocked"] == 1


def test_scenario_c_records_failure_and_rule_proposal_without_enforcement(tmp_path: Path) -> None:
    stream = _combined_stream(tmp_path)
    events = EvidenceStore(stream).read_all()
    failure = next(event for event in events if event.event_type == "failure.observed")
    proposal = next(event for event in events if event.event_type == "rule.proposed")

    assert failure.payload["failure"]["summary"] == "Scenario regression failed before rule proposal"
    assert proposal.payload["proposal"]["rule_id"] == "rule_product_coherence_regression"
    assert proposal.payload["enforced"] is False
    assert proposal.payload["policy_action"] == "none"


def test_scenario_d_answers_which_traceability_gap_exists(tmp_path: Path) -> None:
    stream = _combined_stream(tmp_path)
    gap = next(event for event in EvidenceStore(stream).read_all() if event.event_type == "aspice.check.completed")

    assert gap.subject == {"kind": "traceability_gap", "id": "SW-REQ-AUTH-007"}
    assert gap.payload["missing_link"] == "verification_case"
    assert gap.payload["source_file"] == "docs/requirements/auth.md"


def test_scenario_e_combined_timeline_is_valid_and_meaningful(tmp_path: Path) -> None:
    stream = _combined_stream(tmp_path)
    validation = validate_event_stream(stream)
    summary = summarize_event_stream(stream)

    assert validation == {"valid": True, "events": 7, "errors": []}
    assert summary["events"] == 7
    assert summary["event_types"] == {
        "accountable_change.evidence.generated": 1,
        "agent.run.completed": 1,
        "aspice.check.completed": 1,
        "change_request.evidence.generated": 1,
        "failure.observed": 1,
        "rule.proposed": 1,
        "safety_guard.action.blocked": 1,
    }
    assert "failure_loop_rule_proposal" in summary["subjects"]
    assert "safety_guard_action" in summary["subjects"]


def test_registry_contributes_to_product_scenarios_and_fails_closed() -> None:
    descriptors = {descriptor.adapter_id: descriptor for descriptor in list_adapter_descriptors()}

    assert set(descriptors) == {"agent-evidence-plane", "safety-guard", "failure-loop"}
    assert all(descriptor.execution_mode == "translation-only" for descriptor in descriptors.values())
    assert descriptors["failure-loop"].supported_event_types == ("failure.observed", "rule.proposed")

    missing = runner.invoke(app, ["evidence", "adapter", "show", "unknown-adapter"])
    assert missing.exit_code == 1


def test_scaffold_ui_surface_can_show_future_product_results_without_ui_rewrite() -> None:
    ui = get_scaffolding_slice("ui")
    editor = get_scaffolding_slice("editor")

    assert ui.status == "existing-app-preserved"
    assert "src/core/app.py" in ui.source_paths
    assert "src/ui/widgets/process_monitor.py" in ui.source_paths
    assert "src/ui/widgets/terminal.py" in ui.source_paths
    assert "src/ui/widgets/file_browser.py" in ui.source_paths
    assert "src/ui/widgets/code_editor.py" in editor.source_paths
    assert "no UI rewrite" in ui.excluded_scope
    assert "no production dashboard claim" in ui.excluded_scope


def test_scaffold_cli_still_reports_original_matrix_ui() -> None:
    result = runner.invoke(app, ["scaffold", "show", "ui"])

    assert result.exit_code == 0
    assert "Original Matrix UI" in result.output
    assert "src/core/app.py" in result.output
    assert "src/ui/widgets/matrix_rain.py" in result.output
