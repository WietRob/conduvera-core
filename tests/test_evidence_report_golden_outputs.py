"""Golden-output regression tests for Matrix OS evidence operator reports."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from curaops.cli.main import app
from curaops.evidence import ValidationError, validate_event_stream
from curaops.evidence.reporting import build_operator_report, render_operator_report

runner = CliRunner()

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evidence" / "operator_report"
EVENTS_PATH = FIXTURE_DIR / "product_coherence.events.jsonl"
EXPECTED_TEXT = FIXTURE_DIR / "product_coherence.expected.txt"
EXPECTED_MARKDOWN = FIXTURE_DIR / "product_coherence.expected.md"
EXPECTED_JSON = FIXTURE_DIR / "product_coherence.expected.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_golden_fixture_jsonl_validates_as_event_envelope_stream() -> None:
    assert validate_event_stream(EVENTS_PATH) == {"valid": True, "events": 7, "errors": []}


def test_text_output_matches_golden_file() -> None:
    report = build_operator_report(EVENTS_PATH)

    assert render_operator_report(report, format="text") == _read(EXPECTED_TEXT)


def test_markdown_output_matches_golden_file() -> None:
    report = build_operator_report(EVENTS_PATH)

    assert render_operator_report(report, format="markdown") == _read(EXPECTED_MARKDOWN)


def test_json_output_matches_golden_file() -> None:
    report = build_operator_report(EVENTS_PATH)

    assert json.loads(render_operator_report(report, format="json")) == json.loads(_read(EXPECTED_JSON))
    assert render_operator_report(report, format="json") == _read(EXPECTED_JSON)


def test_golden_report_locks_operator_accountability_answers() -> None:
    report = build_operator_report(EVENTS_PATH)
    text = render_operator_report(report, format="text")
    report_json = report.to_dict()

    assert report_json["event_types"]["change_request.evidence.generated"] == 1
    assert "approved" in text
    assert report_json["event_types"]["accountable_change.evidence.generated"] == 1
    assert report_json["event_types"]["agent.run.completed"] == 1
    assert report_json["requirements"] == ["SW-REQ-AUTH-007"]
    assert report_json["traceability_gaps"] == [
        {
            "requirement_id": "SW-REQ-AUTH-007",
            "missing_link": "verification_case",
            "source_file": "docs/requirements/auth.md",
        }
    ]
    assert report_json["blocked_actions"][0]["action"] == "rm production.db"
    assert report_json["failures"][0]["summary"] == "Scenario regression failed before rule proposal"
    assert report_json["rule_proposals"][0]["rule_id"] == "rule_product_coherence_regression"
    assert report_json["rule_proposals"][0]["enforced"] is False
    assert report_json["rule_proposals"][0]["policy_action"] == "none"
    assert report_json["adapters"] == {
        "matrix-os.agent-evidence-plane": 1,
        "matrix-os.failure-loop": 2,
        "matrix-os.safety-guard": 1,
        "native": 3,
    }


def test_missing_golden_fixture_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.events.jsonl"

    with pytest.raises(ValidationError):
        build_operator_report(missing)

    result = runner.invoke(app, ["evidence", "report", str(missing), "--format", "text"])

    assert result.exit_code == 1
    assert "Evidence report failed" in result.output


def test_intentional_output_changes_must_update_golden_files() -> None:
    report = build_operator_report(EVENTS_PATH)

    assert render_operator_report(report, format="text") == _read(EXPECTED_TEXT)
    assert render_operator_report(report, format="markdown") == _read(EXPECTED_MARKDOWN)
    assert render_operator_report(report, format="json") == _read(EXPECTED_JSON)
