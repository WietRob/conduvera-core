"""Regression tests for PR #5 review blockers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

from curaops.cli.main import app
from curaops.skills.change_request import ChangeRequestService, CRStatus, RootCauseCategory


runner = CliRunner()


def _make_verified_bugfix(svc: ChangeRequestService):
    cr = svc.create_cr(
        title="Fix reviewed bugfix lifecycle",
        requester="dev@example.com",
        problem="A reviewed bugfix needs root cause metadata before closure",
        justification="Review blocker requires lifecycle validation coverage",
        change_type="bugfix",
        requirement_linkage_type="existing_ref",
        impact_level=["SW"],
        requirement_refs=["SW-REQ-900"],
        safety_impact="none",
    )
    svc.submit_cr(cr.id)
    svc.approve_cr(cr.id, reviewer="lead@example.com")
    svc.start_cr(cr.id)
    svc.complete_cr(
        cr.id,
        affected_files=["src/reviewed.py"],
        affected_verifications=["TC-SVT-900"],
        commits=["abc123"],
    )
    svc.generate_evidence(cr.id)
    svc.verify_cr(cr.id)
    return cr


def test_bugfix_close_requires_root_cause_category(tmp_path):
    svc = ChangeRequestService(
        changes_dir=tmp_path / "changes",
        evidence_dir=tmp_path / "evidence",
    )
    cr = _make_verified_bugfix(svc)

    with pytest.raises(ValueError, match="root_cause_category"):
        svc.close_cr(cr.id)

    assert svc.check_status(cr.id) == CRStatus.VERIFIED


def test_bugfix_close_accepts_and_persists_root_cause_category(tmp_path):
    svc = ChangeRequestService(
        changes_dir=tmp_path / "changes",
        evidence_dir=tmp_path / "evidence",
    )
    cr = _make_verified_bugfix(svc)

    closed = svc.close_cr(cr.id, root_cause_category="impl_bug")

    assert closed.status == CRStatus.CLOSED
    assert closed.root_cause_category == RootCauseCategory.IMPL_BUG
    assert svc.get_cr(cr.id).root_cause_category == RootCauseCategory.IMPL_BUG


def test_cli_close_accepts_root_cause_category(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    svc = ChangeRequestService(
        changes_dir=tmp_path / "changes",
        evidence_dir=tmp_path / "changes" / "evidence",
    )
    cr = _make_verified_bugfix(svc)

    result = runner.invoke(app, ["cr", "close", cr.id, "--root-cause-category", "impl_bug"])

    assert result.exit_code == 0, result.output
    assert ChangeRequestService(
        changes_dir=tmp_path / "changes",
        evidence_dir=tmp_path / "changes" / "evidence",
    ).get_cr(cr.id).root_cause_category == RootCauseCategory.IMPL_BUG


def test_cli_emergency_submit_accepts_post_mortem_and_rollback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    create = runner.invoke(
        app,
        [
            "cr",
            "create",
            "--title",
            "Hotfix reviewed production incident",
            "--problem",
            "Sensitive production behavior requires an immediate emergency fix",
            "--justification",
            "Production incident response requires submitting a retroactive CR",
            "--change-type",
            "bugfix",
            "--requirement-linkage-type",
            "existing_ref",
            "--impact-level",
            "SW",
            "--requirement-refs",
            "SW-REQ-901",
            "--safety-impact",
            "none",
            "--emergency",
            "--incident-id",
            "INC-2026-901",
            "--severity",
            "P0",
        ],
    )
    assert create.exit_code == 0, create.output
    cr_id = next(line.split()[2] for line in create.output.splitlines() if "Created CR-" in line)

    submitted = runner.invoke(
        app,
        [
            "cr",
            "submit",
            cr_id,
            "--post-mortem-date",
            "2026-05-15T10:00:00Z",
            "--rollback-plan",
            "Revert the hotfix commit and restore the previous deployment artifact",
        ],
    )

    assert submitted.exit_code == 0, submitted.output
    loaded = ChangeRequestService(
        changes_dir=tmp_path / "changes",
        evidence_dir=tmp_path / "changes" / "evidence",
    ).get_cr(cr_id)
    assert loaded.status == CRStatus.SUBMITTED
    assert loaded.post_mortem_date == datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc)
    assert loaded.rollback_plan == "Revert the hotfix commit and restore the previous deployment artifact"
