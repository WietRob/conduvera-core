"""Contract-version regression tests for Matrix OS evidence operator reports."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from curaops.cli.main import app
from curaops.evidence.reporting import REPORT_SCHEMA_VERSION, build_operator_report, render_operator_report

runner = CliRunner()

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evidence" / "operator_report"
EVENTS_PATH = FIXTURE_DIR / "product_coherence.events.jsonl"
EXPECTED_TEXT = FIXTURE_DIR / "product_coherence.expected.txt"
EXPECTED_MARKDOWN = FIXTURE_DIR / "product_coherence.expected.md"
EXPECTED_JSON = FIXTURE_DIR / "product_coherence.expected.json"


def test_report_contract_version_constant_is_stable() -> None:
    assert REPORT_SCHEMA_VERSION == "MXOS-REPORT-1.0"


def test_report_object_exposes_contract_version() -> None:
    report = build_operator_report(EVENTS_PATH)

    assert report.report_schema_version == REPORT_SCHEMA_VERSION
    assert report.to_dict()["report_schema_version"] == REPORT_SCHEMA_VERSION


def test_json_output_and_golden_file_include_contract_version() -> None:
    report = build_operator_report(EVENTS_PATH)
    rendered = json.loads(render_operator_report(report, format="json"))
    golden = json.loads(EXPECTED_JSON.read_text(encoding="utf-8"))

    assert rendered["report_schema_version"] == REPORT_SCHEMA_VERSION
    assert golden["report_schema_version"] == REPORT_SCHEMA_VERSION
    assert rendered == golden


def test_text_and_markdown_outputs_include_contract_version_metadata() -> None:
    report = build_operator_report(EVENTS_PATH)

    text = render_operator_report(report, format="text")
    markdown = render_operator_report(report, format="markdown")

    assert f"Report contract: {REPORT_SCHEMA_VERSION}" in text
    assert f"Report contract: `{REPORT_SCHEMA_VERSION}`" in markdown
    assert text == EXPECTED_TEXT.read_text(encoding="utf-8")
    assert markdown == EXPECTED_MARKDOWN.read_text(encoding="utf-8")


def test_cli_report_contract_discovery_outputs_stable_version() -> None:
    result = runner.invoke(app, ["evidence", "report-contract"])

    assert result.exit_code == 0
    assert result.output.strip() == REPORT_SCHEMA_VERSION


def test_cli_json_report_uses_same_contract_version_as_golden_fixture() -> None:
    result = runner.invoke(app, ["evidence", "report", str(EVENTS_PATH), "--format", "json"])

    assert result.exit_code == 0
    assert json.loads(result.output)["report_schema_version"] == REPORT_SCHEMA_VERSION
    assert result.output == EXPECTED_JSON.read_text(encoding="utf-8")


def test_report_contract_changes_require_golden_updates() -> None:
    report = build_operator_report(EVENTS_PATH)

    assert render_operator_report(report, format="text") == EXPECTED_TEXT.read_text(encoding="utf-8")
    assert render_operator_report(report, format="markdown") == EXPECTED_MARKDOWN.read_text(encoding="utf-8")
    assert render_operator_report(report, format="json") == EXPECTED_JSON.read_text(encoding="utf-8")
