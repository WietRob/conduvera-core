"""Separate authority-plane CLI for issuing manual Buildroom capabilities."""

from pathlib import Path

import pytest

import buildroom_authorization
from buildroom_core import ProjectPack


def make_pack(tmp_path: Path) -> ProjectPack:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    return ProjectPack.from_mapping(
        {
            "project_name": "synthetic-issue",
            "repo_path": str(repo),
            "evidence_dir": str(tmp_path / "evidence"),
            "autopilot_enabled": False,
            "delivery_mode": "engineering_finish_line",
            "allowed_phases": ["RESEARCHER"],
            "profiles": {
                "researcher": "researcher",
                "dreamer": "dreamer",
                "builder": "builder",
                "reviewer": "reviewer",
                "reporter": "orchestrator",
            },
            "execution": {"builder_backend": "native", "reviewer_backend": "native"},
        }
    )


def test_issue_cli_has_no_caller_supplied_issuer():
    with pytest.raises(SystemExit):
        buildroom_authorization.parse_args(
            ["issue", "--project", "synthetic", "--phase", "RESEARCHER", "--request-id", "req-1", "--issuer", "owner"]
        )


def test_issue_cli_resolves_pack_and_prints_only_opaque_id(monkeypatch, tmp_path, capsys):
    pack = make_pack(tmp_path)
    calls = []
    monkeypatch.setattr(buildroom_authorization, "resolve_project", lambda _project: pack)
    monkeypatch.setattr(
        buildroom_authorization,
        "issue_manual_authorization",
        lambda supplied_pack, **kwargs: calls.append((supplied_pack, kwargs)) or "manual-auth-opaque",
    )
    rc = buildroom_authorization.main(
        [
            "issue",
            "--project",
            "synthetic",
            "--phase",
            "RESEARCHER",
            "--request-id",
            "owner-request-1",
            "--dry-run-only",
            "--ttl-seconds",
            "120",
        ]
    )
    assert rc == 0
    assert capsys.readouterr().out.strip() == "manual-auth-opaque"
    assert calls == [
        (
            pack,
            {
                "phase": "RESEARCHER",
                "request_id": "owner-request-1",
                "dry_run_only": True,
                "ttl_seconds": 120,
            },
        )
    ]
