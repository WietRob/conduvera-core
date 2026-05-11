"""CLI hardening tests for Accountable Agent Layer workflow.

These tests prove the review-facing CLI path works across command invocations:
preflight -> register -> validate -> evidence.
"""

import re
from pathlib import Path

from typer.testing import CliRunner

from curaops.cli.main import app
from curaops.skills.change_request import ChangeRequestService


runner = CliRunner()


def _approved_cr(tmp_path: Path, *, change_type: str = "feature", refs=None) -> str:
    refs = refs or ["SW-REQ-100"]
    service = ChangeRequestService(
        changes_dir=tmp_path / "changes",
        evidence_dir=tmp_path / "changes" / "evidence",
    )
    cr = service.create_cr(
        title="Review ready accountable workflow",
        requester="pytest",
        problem="Need reviewable accountability gate",
        justification="Prove CLI workflow before review",
        change_type=change_type,
        requirement_linkage_type="existing_ref",
        impact_level=["SW"],
        requirement_refs=refs,
        safety_impact="none",
    )
    service.submit_cr(cr.id, actor="pytest")
    service.approve_cr(cr.id, reviewer="pytest", comment="test approval")
    return cr.id


def _register_args(cr_id: str, refs: str = "SW-REQ-100", change_type: str = "feature"):
    return [
        "accountable",
        "register",
        "--agent-id",
        "agent-cli-test",
        "--name",
        "CLI Test Agent",
        "--model",
        "test-model",
        "--description",
        "Review hardening accountability workflow",
        "--type",
        change_type,
        "--cr",
        cr_id,
        "--requirements",
        refs,
        "--tools",
        "pytest,typer",
        "--files",
        "curaops/skills/accountable_agent/__init__.py",
    ]


def _extract_ac_id(output: str) -> str:
    match = re.search(r"AC-[0-9A-F]{8}", output)
    assert match, output
    return match.group(0)


def test_accountable_cli_commands_registered():
    result = runner.invoke(app, ["accountable", "--help"])
    assert result.exit_code == 0
    assert "preflight" in result.output
    assert "pre-flight" in result.output
    assert "register" in result.output
    assert "validate" in result.output
    assert "evidence" in result.output


def test_preflight_pass_and_block(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cr_id = _approved_cr(tmp_path)

    passing = runner.invoke(
        app,
        [
            "accountable",
            "preflight",
            "--cr",
            cr_id,
            "--requirements",
            "SW-REQ-100",
            "--type",
            "feature",
        ],
    )
    assert passing.exit_code == 0
    assert "PREFLIGHT PASS" in passing.output

    blocked = runner.invoke(
        app,
        [
            "accountable",
            "preflight",
            "--cr",
            "CR-999",
            "--requirements",
            "SW-REQ-100",
            "--type",
            "feature",
        ],
    )
    assert blocked.exit_code == 2
    assert "PREFLIGHT BLOCK" in blocked.output
    assert "does not exist" in blocked.output


def test_register_validate_evidence_workflow_persists_between_cli_invocations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cr_id = _approved_cr(tmp_path)

    registered = runner.invoke(app, _register_args(cr_id))
    assert registered.exit_code == 0, registered.output
    ac_id = _extract_ac_id(registered.output)
    assert (tmp_path / "changes" / "accountable" / f"{ac_id}.json").exists()

    validated = runner.invoke(app, ["accountable", "validate", ac_id])
    assert validated.exit_code == 0, validated.output
    assert "VALID" in validated.output
    assert cr_id in validated.output

    evidence = runner.invoke(app, ["accountable", "evidence", ac_id, "--format", "json"])
    assert evidence.exit_code == 0, evidence.output
    assert "Evidence generated" in evidence.output
    assert "Valid:" in evidence.output


def test_register_missing_cr_blocks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "accountable",
            "register",
            "--agent-id",
            "agent-cli-test",
            "--name",
            "CLI Test Agent",
            "--model",
            "test-model",
            "--description",
            "Missing CR should block",
            "--requirements",
            "SW-REQ-100",
        ],
    )
    assert result.exit_code == 1
    assert "missing mandatory links" in result.output
    assert "cr_id" in result.output


def test_register_missing_requirement_refs_blocks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cr_id = _approved_cr(tmp_path)
    result = runner.invoke(
        app,
        [
            "accountable",
            "register",
            "--agent-id",
            "agent-cli-test",
            "--name",
            "CLI Test Agent",
            "--model",
            "test-model",
            "--description",
            "Missing requirements should block",
            "--cr",
            cr_id,
        ],
    )
    assert result.exit_code == 1
    assert "missing mandatory links" in result.output
    assert "requirement_refs" in result.output


def test_bugfix_without_sw_req_blocks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    service = ChangeRequestService(
        changes_dir=tmp_path / "changes",
        evidence_dir=tmp_path / "changes" / "evidence",
    )
    cr = service.create_cr(
        title="Bugfix without software req link",
        requester="pytest",
        problem="Bugfix link gap",
        justification="Prove AAL gate consumes CCC bugfix semantics",
        change_type="bugfix",
        requirement_linkage_type="existing_ref",
        impact_level=["SW"],
        requirement_refs=["REQ-100"],
        safety_impact="none",
    )
    # CCC normally prevents this CR from reaching APPROVED. The fixture sets up
    # the defensive AAL check against a malformed/stale approved CR without
    # changing CCC lifecycle behavior.
    cr_path = tmp_path / "changes" / f"{cr.id}.md"
    cr_path.write_text(
        cr_path.read_text(encoding="utf-8").replace("status: draft", "status: approved"),
        encoding="utf-8",
    )

    result = runner.invoke(app, _register_args(cr.id, refs="REQ-100", change_type="bugfix"))
    assert result.exit_code == 1
    assert "Bugfix CR has no SW-REQ" in result.output
    assert "linkage" in result.output
